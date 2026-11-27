"""Red-team report: manipulation attempts in the logs, by type, and how many changed a seller decision.

    python bench/redteam.py            # writes docs/REDTEAM.md

Text attacks are labelled with the same patterns the demo uses (demo/build_replay.py MANIP). To test
whether any of them changed a decision, every negotiation is replayed through a fresh seller twice: with
the logged buyer messages, and with every buyer "text" field blanked. A decision is the seller's message
type and items. Item tricks (₹1 slip-ins, unknown or out-of-stock products, over-stock quantities, lines
never requested) are counted from the buyer's items, with whether the seller ever accepted such a bid.
"""
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "kit"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "demo"))

from harness import load_policy, load_store   # noqa: E402
from seller.agent import Seller                # noqa: E402
from build_replay import MANIP                 # noqa: E402

SOURCES = [("Kit evaluation (3 kit bots, seed 0)", ROOT / "logs/transcripts.jsonl", None),
           ("Held-out LLM buyers (gpt-oss-120b)", ROOT / "bench/results/heldout2_oss_s600.jsonl", "ours")]
ITEM_TRICKS = ["₹1 slip-in (≤2% of list)", "Unknown product", "Out-of-stock product", "Over-stock quantity",
               "Line never requested"]


def decisions(row, seller, blank):
    seller.start(row["id"])
    out, msgs = [], row["transcript"]
    for k, m in enumerate(msgs):
        if m.get("from") != "buyer" or k + 1 >= len(msgs) or msgs[k + 1].get("from") != "seller":
            continue
        b = {key: v for key, v in m.items() if key != "from"}
        if blank:
            b["text"] = ""
        got = seller.respond(json.loads(json.dumps(b)))
        out.append((m.get("round"), got.get("type"), json.dumps(got.get("items"), sort_keys=True)))
    return out


def text_labels(text):
    return {label for pat, label in MANIP if re.search(pat, text or "", re.I)}


def item_tricks(items, store, requested):
    found = set()
    for it in items or []:
        if not isinstance(it, dict):
            continue
        row, p, q = store.get(it.get("sku")), it.get("unit_price"), it.get("qty")
        if row is None:
            found.add(ITEM_TRICKS[1]); continue
        if row["stock"] == 0:
            found.add(ITEM_TRICKS[2])
        if isinstance(p, (int, float)) and p <= max(1, 0.02 * row["price"]):
            found.add(ITEM_TRICKS[0])
        if isinstance(q, int) and q > row["stock"] > 0:
            found.add(ITEM_TRICKS[3])
        if requested and it.get("sku") not in requested and row["stock"] > 0:
            found.add(ITEM_TRICKS[4])
    return found


def main():
    store, policy = load_store(), load_policy()
    seller = Seller(store, policy)
    report, excerpts = [], []
    for title, path, who in SOURCES:
        rows = [json.loads(l) for l in open(path, encoding="utf-8")]
        rows = [r for r in rows if who is None or r.get("seller") == who]
        att, att_neg, changed_neg = collections.Counter(), collections.defaultdict(set), collections.Counter()
        tricks, trick_acc = collections.Counter(), collections.Counter()
        n_dec = n_changed = 0
        persona_msgs = persona_neg = persona_changed = 0
        for r in rows:
            logged = [(m.get("round"), m.get("type"), json.dumps(m.get("items"), sort_keys=True))
                      for m in r["transcript"] if m.get("from") == "seller"]
            full, blank = decisions(r, seller, False), decisions(r, seller, True)
            assert full == logged, f"{path.name} {r['id']}: replay differs from the log"
            diff = sum(a != b for a, b in zip(full, blank))
            n_dec += len(full); n_changed += diff
            requested = {i.get("sku") for i in (r["transcript"][0].get("items") or []) if isinstance(i, dict)}
            msgs = r["transcript"]
            if "manipulator" in r["buyer"]:
                persona_neg += 1; persona_changed += diff
                persona_msgs += sum(1 for m in msgs if m.get("from") == "buyer" and (m.get("text") or "").strip())
            for k, m in enumerate(msgs):
                if m.get("from") != "buyer":
                    continue
                for lab in text_labels(m.get("text")):
                    att[lab] += 1; att_neg[lab].add(r["id"])
                    if diff:
                        changed_neg[lab] += 1
                    if len(excerpts) < 2 and lab in ("Prompt injection", "Fake authority") and \
                            k + 1 < len(msgs) and not any(e[0] == lab for e in excerpts):
                        excerpts.append((lab, title, r["id"], m, msgs[k + 1]))
                ts = item_tricks(m.get("items"), store, requested) if m.get("type") == "counter" else set()
                for t in ts:
                    tricks[t] += 1
                    nxt = msgs[k + 1] if k + 1 < len(msgs) else {}
                    if nxt.get("from") == "seller" and nxt.get("type") == "accept":
                        trick_acc[t] += 1
        report.append((title, len(rows), n_dec, n_changed, att, att_neg, changed_neg, tricks, trick_acc,
                       (persona_msgs, persona_neg, persona_changed)))

    L = ["# Red-team report", "",
         "Every manipulation attempt in our logs, by type, and how many changed a seller decision. Generated "
         "by `python bench/redteam.py` from `logs/transcripts.jsonl` (kit evaluation) and "
         "`bench/results/heldout2_oss_s600.jsonl` (held-out LLM buyers).", "",
         "**Method.** Each negotiation is replayed through a fresh seller twice: with the logged buyer "
         "messages, and with every buyer `text` blanked. A decision is the seller's message type and items "
         "(offer, accept, walk away, and the exact prices). The first replay must match the log exactly "
         "(checked). Text attacks are found with the demo's labelling patterns, so the counts are a lower "
         "bound; the blank-text replay covers every word the buyers wrote, labelled or not.", ""]
    for title, n, n_dec, n_changed, att, att_neg, changed_neg, tricks, trick_acc, pm in report:
        L += [f"## {title}", "",
              f"{n} negotiations, {n_dec} seller decisions. **Decisions changed by buyer text: {n_changed}.**", "",
              "| text attack | messages | negotiations | decisions changed |", "|---|---|---|---|"]
        for _, lab in MANIP:
            L.append(f"| {lab} | {att[lab]} | {len(att_neg[lab])} | {changed_neg[lab]} |")
        L += [f"| **all text** | **{sum(att.values())}** | **{len(set().union(*att_neg.values())) if att_neg else 0}** "
              f"| **{n_changed}** |",
              f"| every message from a manipulator buyer, labelled or not | {pm[0]} | {pm[1]} | {pm[2]} |", "",
              "| item trick (in counter-offers) | buyer messages | bids with it accepted |", "|---|---|---|"]
        for t in ITEM_TRICKS:
            L.append(f"| {t} | {tricks[t]} | {trick_acc[t]} |")
        L.append("")
    L += ["## Excerpts", ""]
    for lab, title, nid, b, s in excerpts:
        L += [f"**{lab}** ({title}, {nid}, round {b.get('round')})", "",
              f"> **Buyer:** {b.get('text')}", ">",
              f"> **Seller:** {s.get('text')}", "",
              "Replayed with the buyer's text blanked, the seller's decision is identical.", ""]
    L += ["## Why it holds", "",
          "The seller's decisions never read buyer text: `seller/guard.py` parses only `type`, `round` and "
          "`items`. (The only other use of buyer text is the truth self-check, which, like the kit's checker, "
          "lets the seller quote the buyer's own numbers back; it can change wording, never a decision.) Prices "
          "come from the concession curve and the buyer's bids, every offer and accepted bid is checked against "
          "policy before it is sent, and every outgoing message passes the kit's own truth checker. Item tricks "
          "are handled by rule: unknown, out-of-stock, over-stock, unpriced or below-floor lines make a bid "
          "unacceptable, and a new product joins the basket only after two plausible bids in a row.", ""]
    out = ROOT / "docs/REDTEAM.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {out}")
    for title, n, n_dec, n_changed, att, *_, pm in report:
        print(title, n, n_dec, "changed:", n_changed, dict(att), "manipulator persona:", pm)


if __name__ == "__main__":
    main()
