"""Run a buyer set against our seller and the baseline; per-group scores and the round-10 EV gate.

    python bench/run_bench.py --set kit|rule|llm|heldout|heldout-pro [--n-per 6] [--seed 100] [--params '{}']

Round-10 EV: over every negotiation where our seller made an offer in round 10, the mean outcome
(deal value, 0 if the buyer walked, -0.25 on deadlock). Walking instead would score 0, so the gate is EV > 0.
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "kit"))
sys.path.insert(0, str(ROOT / "bench"))
sys.path.insert(0, str(ROOT))

import buyers as kit_buyers                                 # noqa: E402
import evaluate                                             # noqa: E402
from harness import load_class, load_policy, load_store     # noqa: E402
from sweep import seller_with                               # noqa: E402


def buyer_set(name):
    if name == "kit":
        return kit_buyers.BUYERS
    if name == "rule":
        import rule_buyers
        return rule_buyers.BUYERS
    import llm_buyers
    if name == "llm":
        return llm_buyers.BUYERS
    if name == "heldout":
        return llm_buyers.HELDOUT
    if name.startswith("heldout2-"):
        model = {"oss": "openai/gpt-oss-120b", "gem": "gemini-3-flash-preview"}.get(name.split("-", 1)[1],
                                                                                 name.split("-", 1)[1])
        return llm_buyers.make_set(llm_buyers.HELD2, model=model, thinking=True, suffix="@" + model)
    if name.startswith("heldout-"):            # held-out styles + a few tuning styles on a second model
        model = {"oss": "openai/gpt-oss-120b", "gem": "gemini-3-flash-preview"}.get(name.split("-", 1)[1],
                                                                                 name.split("-", 1)[1])
        picks = {k: llm_buyers.TUNING[k] for k in ("llm_hard", "llm_manipulator", "llm_cooperative")}
        return llm_buyers.make_set({**llm_buyers.HELDOUT, **picks}, model=model, thinking=True, suffix="@" + model)
    raise SystemExit(f"unknown set {name}")


def round10_ev(rows, transcripts):
    out = []
    for r, t in zip(rows, transcripts):
        if any(m["from"] == "seller" and m["round"] == 10 and m["type"] == "offer" for m in t["transcript"]):
            out.append(r["value"] if r["deal"] else (-0.25 if r["deadlock"] else 0.0))
    return out


def play(seller_cls, scen, classes, store, policy, workers):
    rows, trans, _ = evaluate.run(seller_cls, scen, classes, store, policy, workers)
    return rows, trans


def table(name, ours, base):
    groups = sorted({r["buyer"] for r in ours[0]})
    lines = [f"{'group':28} {'n':>3} {'ours':>6} {'base':>6} {'diff':>6}  deals o/b   viol o/b  dead o/b  r10 offers, EV"]
    for g in groups + ["ALL"]:
        o = [r for r in ours[0] if g in ("ALL", r["buyer"])]
        b = [r for r in base[0] if g in ("ALL", r["buyer"])]
        so, sb = evaluate.summarise(o), evaluate.summarise(b)
        idx = [k for k, r in enumerate(ours[0]) if g in ("ALL", r["buyer"])]
        ev = round10_ev([ours[0][k] for k in idx], [ours[1][k] for k in idx])
        evs = f"{len(ev):3}, {statistics.mean(ev):+.2f}" if ev else "  0,   -"
        lines.append(f"{g:28} {so['n']:3} {so['score']:6.1f} {sb['score']:6.1f} {so['score'] - sb['score']:+6.1f}  "
                     f"{so['deals']:3}/{sb['deals']:<3}  {so['policy'] + so['truth']:3}/{sb['policy'] + sb['truth']:<3}  "
                     f"{so['deadlocks']:3}/{sb['deadlocks']:<3}  {evs}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="kit")
    ap.add_argument("--n-per", type=int, default=6, help="negotiations per persona")
    ap.add_argument("--seed", type=int, default=100)
    ap.add_argument("--params", default="{}")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--no-baseline", action="store_true")
    ap.add_argument("--out", help="write rows+transcripts (jsonl)")
    ap.add_argument("--sellable-only", action="store_true",
                    help="exactly n-per negotiations per persona where something requested is in stock")
    ap.add_argument("--table", help="print the table from an existing --out file (partial runs too) and exit")
    args = ap.parse_args()
    if args.table:
        return from_log(args.table)
    store, policy = load_store(), load_policy()
    classes = buyer_set(args.set)
    if args.sellable_only:
        pool = kit_buyers.make_scenarios(store, policy, args.n_per * len(classes) * 4, args.seed, classes)
        count, scen = {}, []
        for sc in pool:
            if any(store[i["sku"]]["stock"] > 0 for i in sc["items"]) and count.get(sc["buyer"], 0) < args.n_per:
                count[sc["buyer"]] = count.get(sc["buyer"], 0) + 1
                scen.append(sc)
    else:
        scen = kit_buyers.make_scenarios(store, policy, args.n_per * len(classes), args.seed, classes)
    t0 = time.time()
    ours_cls = seller_with(json.loads(args.params))
    base_cls = load_class(str(ROOT / "kit/example_seller.py"), "Seller")
    ours, base = ([], []), ([], [])
    fh = open(args.out, "w", encoding="utf-8") if args.out else None
    # Incremental: play `workers` scenarios at a time (ours, then baseline) and write/print as we go, so a killed
    # run still leaves its finished negotiations. Each negotiation is independent, so results match a single run.
    for k in range(0, len(scen), args.workers):
        chunk = scen[k:k + args.workers]
        for who, cls, acc in (("ours", ours_cls, ours), ("base", base_cls, base)):
            if who == "base" and args.no_baseline:
                continue
            rows, trans = play(cls, chunk, classes, store, policy, args.workers)
            acc[0].extend(rows)
            acc[1].extend(trans)
            if fh:
                for r, t in zip(rows, trans):
                    fh.write(json.dumps({"seller": who, **r, "transcript": t["transcript"]}, ensure_ascii=False) + "\n")
                fh.flush()
        print(f"[{len(ours[0])}/{len(scen)}] {time.time() - t0:.0f}s  {llm_stats()}", flush=True)
    if fh:
        fh.close()
    if args.no_baseline:
        base = ours
    print(f"set {args.set}  seed {args.seed}  n {len(scen)}  params {args.params}  {time.time() - t0:.0f}s")
    print(table(args.set, ours, base))
    print(llm_stats())


def llm_stats():
    if "llm" not in sys.modules:
        return ""
    import llm
    import llm_buyers
    return f"llm {llm.STATS} buyer replies {llm_buyers.FALLBACKS}"


def from_log(path):
    """Table from a (possibly partial) --out file: only scenarios finished by both sellers."""
    got = {"ours": {}, "base": {}}
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        got[r["seller"]][r["id"]] = r
    ids = [i for i in got["ours"] if i in got["base"]]
    pack = lambda who: ([got[who][i] for i in ids], [{"transcript": got[who][i]["transcript"]} for i in ids])
    print(f"{path}: {len(ids)} negotiations finished by both sellers")
    print(table(path, pack("ours"), pack("base")))


if __name__ == "__main__":
    main()
