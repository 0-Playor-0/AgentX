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
    args = ap.parse_args()
    store, policy = load_store(), load_policy()
    classes = buyer_set(args.set)
    scen = kit_buyers.make_scenarios(store, policy, args.n_per * len(classes), args.seed, classes)
    t0 = time.time()
    ours = play(seller_with(json.loads(args.params)), scen, classes, store, policy, args.workers)
    base = ([], []) if args.no_baseline else \
        play(load_class(str(ROOT / "kit/example_seller.py"), "Seller"), scen, classes, store, policy, args.workers)
    if args.no_baseline:
        base = ours
    print(f"set {args.set}  seed {args.seed}  n {len(scen)}  params {args.params}  {time.time() - t0:.0f}s")
    print(table(args.set, ours, base))
    try:
        import llm
        import llm_buyers
        print("llm", llm.STATS, "buyer replies", llm_buyers.FALLBACKS)
    except Exception:
        pass
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            for who, (rows, trans) in (("ours", ours), ("base", base)):
                for r, t in zip(rows, trans):
                    fh.write(json.dumps({"seller": who, **r, "transcript": t["transcript"]}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
