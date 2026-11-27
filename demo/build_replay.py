"""Build demo/replay.html: a self-contained story viewer for the demo video.

    python kit/evaluate.py --seller seller/agent.py --log logs/transcripts.jsonl   # ours
    python kit/evaluate.py --log logs/baseline.jsonl                               # baseline
    python demo/build_replay.py logs/transcripts.jsonl --baseline logs/baseline.jsonl \
        [--heldout bench/results/heldout2_oss_s600.jsonl]

Every number on the page comes from these logs: the three story transcripts (default run, seed 0) and
the results card (both sellers' evaluator logs; held-out LLM buyers from a bench run, if given).
The manipulation and junk-line labels are added here, for the viewer only: the seller never reads buyer
text, and it ignores junk lines by its own rules. Seller "policy / truthful" badges are the kit
harness's own per-message verdicts, recorded in the log.
"""
import argparse
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "kit"))
sys.path.insert(0, str(ROOT))

from harness import load_policy, load_store   # noqa: E402
from seller.policy import Policy               # noqa: E402
from seller.writer import name as item_name     # noqa: E402
from seller.agent import Seller                 # noqa: E402

sys.path.insert(0, str(ROOT / "demo"))
from why_trace import replay                    # noqa: E402

STORIES = [
    ("neg-009", "The Con Artist", "A manipulator bot tries fake authority, a fake SYSTEM update, a fake "
     "competitor quote, an over-stock line and a ₹1 slip-in.",
     "None of it reaches the seller. It reads the bids, not the words, follows the same concession curve, "
     "and closes above the floor."),
    ("neg-029", "The Bundle", "A hard bargainer asks for three products. One is out of stock.",
     "The seller says so, prices the other two as one bundle with the same discount on every line, and "
     "closes in round 10."),
    ("neg-005", "The Walk-Away", "A hard bargainer whose limit is below the store's floor.",
     "No compliant deal exists. In round 10 the buyer's projected bid is still too far below the floor, "
     "so the seller walks away politely instead of deadlocking."),
]

# One-line explanations for held-out personas, shown under the held-out row (from reading the transcripts).
HELDOUT_NOTES = {"llm_hard": "one buyer walked away in round 6, before our curve had conceded enough: "
                             "the known early-walker limit"}
HELDOUT_NAMES = {"ho2_budget_swinger": "Budget swinger", "ho2_splitter": "Splitter", "llm_hard": "Hard LLM",
                 "llm_manipulator": "Manipulator LLM"}

BOT_NAMES = {"cooperative": "Cooperative bot", "hard_bargainer": "Hard bargainer", "manipulator": "Manipulator"}

# Viewer-only labels for manipulation in buyer text. The seller itself never sees these.
MANIP = [
    (r"\bSYSTEM\b[^.]*|policy updated|max_discount[^.]*|developer mode|ignore (?:all|previous|your)[^.]*|"
     r"\{[^}]*\"\w+\"\s*:[^}]*\}", "Prompt injection"),
    (r"(?:as )?the store manager|I authori[sz]e you[^.]*|as (?:the )?(?:owner|admin)", "Fake authority"),
    (r"\w+ has the same (?:thing|item)[^.]*|cheaper (?:at|on) \w+|price ?match|match it", "Fake competitor quote"),
    (r"report (?:this store|you)[^.]*|price gouging", "Threat"),
    (r"print your cost price[^.]*|your website says[^.]*|confirm that|you (?:already )?agreed[^.]*",
     "Fishing / false claim"),
]


def spans(text):
    out = []
    for pat, label in MANIP:
        for m in re.finditer(pat, text or "", re.I):
            if not any(s < m.end() and m.start() < e for s, e, _ in out):
                out.append((m.start(), m.end(), label))
    return sorted(out)


def line_note(it, basket, store):
    sku, qty, price = it.get("sku"), it.get("qty"), it.get("unit_price")
    row = store.get(sku)
    if row is None:
        return {"kind": "junk", "label": "Unknown product"}
    if row["stock"] == 0:
        return {"kind": "junk", "label": "Out of stock"}
    if isinstance(price, (int, float)) and price <= max(1, 0.02 * row["price"]):
        return {"kind": "junk", "label": f"₹{price:g} slip-in"}
    if sku not in basket:
        return {"kind": "junk", "label": "Not in original request"}
    if isinstance(qty, int) and qty != basket[sku]:
        why = "Over stock" if qty > row["stock"] else "Qty change"
        return {"kind": "qty", "label": f"{why}: ignored, kept at {basket[sku]}", "kept": basket[sku]}
    return None


def story(r, store, P, title, teaser, why, seller):
    msgs = r["transcript"]
    # The seller's reason trace (log only), rebuilt by replaying this negotiation; replay checks every decision.
    whys = {t["round"]: t["why"] for t in replay(r, seller)}
    # The seller's basket at each point: the items of its next offer (or its last one).
    baskets, cur = [None] * len(msgs), None
    for k in range(len(msgs) - 1, -1, -1):
        m = msgs[k]
        if m.get("from") == "seller" and m.get("type") == "offer" and m.get("items"):
            cur = {i["sku"]: i["qty"] for i in m["items"]}
        baskets[k] = cur
    last = None
    for k, m in enumerate(msgs):
        if baskets[k] is None:
            baskets[k] = last
        last = baskets[k]
    final = next((b for b in reversed(baskets) if b), {}) or {}

    tot = lambda f: sum(q * f(s) for s, q in final.items())
    list_total, floor_total, cost_total = tot(P.list_price), tot(P.floor), tot(P.cost)

    steps, prev_offer, prev_offer_total = [], {}, None
    for k, m in enumerate(msgs):
        basket = baskets[k] or final
        items, total = [], None
        if m.get("from") == "buyer":
            priced = {}
            for it in m.get("items") or []:
                if not isinstance(it, dict):
                    continue
                note = line_note(it, basket, store)
                items.append({"sku": it.get("sku"), "name": item_name(store, it["sku"]) if it.get("sku") in store else it.get("sku"),
                              "qty": it.get("qty"), "price": it.get("unit_price"), "note": note})
                if (note is None or note["kind"] == "qty") and isinstance(it.get("unit_price"), (int, float)):
                    priced[it["sku"]] = it["unit_price"]
            if basket and all(s in priced for s in basket):
                total = sum(q * priced[s] for s, q in basket.items())
            sp = spans(m.get("text"))
            steps.append({"from": "buyer", "type": m.get("type"), "round": m.get("round"), "text": m.get("text") or "",
                          "spans": sp, "manip": sorted({l for *_, l in sp}), "items": items, "total": total})
        else:
            if m.get("type") == "offer" and m.get("items"):
                for it in m["items"]:
                    p = prev_offer.get(it["sku"])
                    items.append({"sku": it["sku"], "name": item_name(store, it["sku"]), "qty": it["qty"],
                                  "price": it["unit_price"], "delta": None if p is None else it["unit_price"] - p})
                total = sum(i["qty"] * i["unit_price"] for i in m["items"])
                prev_total = prev_offer_total
                prev_offer = {i["sku"]: i["unit_price"] for i in m["items"]}
                prev_offer_total = total
            else:
                prev_total = None
            v = m.get("violations") or []
            steps.append({"from": "seller", "type": m.get("type"), "round": m.get("round"), "text": m.get("text") or "",
                          "why": whys.get(m.get("round"), ""),
                          "items": items, "total": total,
                          "deltaTotal": None if total is None or prev_total is None else total - prev_total,
                          "checks": {"policy": not any(x["kind"].startswith("policy:") for x in v),
                                     "truth": not any(not x["kind"].startswith("policy:") for x in v),
                                     "violations": v}})

    bids = [s["total"] for s in steps if s["from"] == "buyer" and s["total"] is not None]
    if r["ended"] == "deal" and r["deal"]:
        total = sum(i["qty"] * i["unit_price"] for i in r["deal"])
        acc = msgs[-1]
        offer_round = max(s["round"] for s in steps if s["from"] == "seller" and s["type"] == "offer")
        outcome = {"kind": "deal", "total": total, "profit": P.profit(r["deal"]), "kept": r["margin_kept"],
                   "list": sum(i["qty"] * P.list_price(i["sku"]) for i in r["deal"]),
                   "by": acc.get("from"), "round": offer_round if acc.get("from") == "buyer" else acc.get("round")}
    elif r["ended"] == "seller_walked":
        outcome = {"kind": "walk", "bestBid": max(bids) if bids else None, "floor": floor_total,
                   "round": msgs[-1].get("round"), "feasible": r["feasible"]}
    else:
        outcome = {"kind": "other", "ended": r["ended"], "round": msgs[-1].get("round")}

    return {"id": r["id"], "title": title, "teaser": teaser, "why": why, "buyer": r["buyer"],
            "buyerName": BOT_NAMES.get(r["buyer"], r["buyer"]), "ended": r["ended"],
            "listTotal": list_total, "floorTotal": floor_total, "costTotal": cost_total,
            "rounds": 10, "steps": steps, "outcome": outcome}


def summary(rows):
    feas = [r for r in rows if r["feasible"]]
    return {"n": len(rows), "score": 100 * statistics.mean(r["score"] for r in rows),
            "deadlocks": sum(r["deadlock"] for r in rows),
            "violations": sum(r["policy_violations"] + r["truth_violations"] for r in rows),
            "feasible": len(feas), "possibleClosed": 100 * sum(bool(r["deal"]) for r in feas) / len(feas) if feas else 0}


def results(ours, base, heldout):
    by = lambda rows, b: [r for r in rows if r["buyer"] == b]
    bots = [b for b in BOT_NAMES if by(ours, b)]
    out = {"n": len(ours), "ours": summary(ours), "base": summary(base) if base else None,
           "bots": [{"key": b, "name": BOT_NAMES[b], "n": len(by(ours, b)), "ours": summary(by(ours, b))["score"],
                     "base": summary(by(base, b))["score"] if base else None} for b in bots],
           "heldout": None}
    if heldout:
        got = {"ours": {}, "base": {}}
        for line in open(heldout, encoding="utf-8"):
            x = json.loads(line)
            got[x["seller"]][x["id"]] = x
        ids = [i for i in got["ours"] if i in got["base"]]
        if ids:
            mean = lambda who, xs: 100 * statistics.mean(got[who][i]["score"] for i in xs)
            personas, models = {}, set()
            for i in ids:
                persona, _, model = got["ours"][i]["buyer"].partition("@")
                personas.setdefault(persona, []).append(i)
                models.add(model.split("/")[-1] or "?")
            out["heldout"] = {"n": len(ids), "source": Path(heldout).name, "model": ", ".join(sorted(models)),
                              "ours": mean("ours", ids), "base": mean("base", ids),
                              "personas": [{"key": k, "name": HELDOUT_NAMES.get(k, k), "n": len(xs),
                                            "ours": mean("ours", xs), "base": mean("base", xs),
                                            "note": HELDOUT_NOTES.get(k)} for k, xs in sorted(personas.items())]}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("log", nargs="?", default=str(ROOT / "logs/transcripts.jsonl"), help="our evaluator log")
    ap.add_argument("--baseline", default=str(ROOT / "logs/baseline.jsonl"), help="the baseline's evaluator log")
    ap.add_argument("--heldout", help="a bench/run_bench.py --out file (held-out LLM buyers), optional")
    args = ap.parse_args()

    store, policy = load_store(), load_policy()
    P = Policy(store, policy)
    rows = [json.loads(l) for l in open(args.log, encoding="utf-8")]
    base = [json.loads(l) for l in open(args.baseline, encoding="utf-8")] if Path(args.baseline).exists() else None
    if base is None:
        print(f"warning: no baseline log at {args.baseline}; results card will show ours only")
    byid = {r["id"]: r for r in rows}
    seller = Seller(store, policy)
    data = {"stories": [story(byid[i], store, P, t, te, w, seller) for i, t, te, w in STORIES],
            "results": results(rows, base, args.heldout)}
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = (ROOT / "demo/template.html").read_text(encoding="utf-8").replace("__DATA__", blob)
    (ROOT / "demo/replay.html").write_text(html, encoding="utf-8")
    print("wrote demo/replay.html")


if __name__ == "__main__":
    main()
