"""Grid sweep of seller strategy params. Selects by worst-case score across buyer groups; reports the mean too.

    python bench/sweep.py --seeds 0 1 2 --grid '{"e":[1,2],"recip":[0,0.5]}' [--buyers bench/rule_buyers.py]
"""
import argparse
import itertools
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "kit"))
sys.path.insert(0, str(ROOT))

import buyers as kit_buyers                                    # noqa: E402
import evaluate                                                 # noqa: E402
from harness import load_policy, load_store                     # noqa: E402
from seller.agent import Seller                                 # noqa: E402


def seller_with(params):
    return type("SweepSeller", (Seller,), {"params": dict(params)})


def score(seller_cls, buyer_classes, seeds, n, store, policy):
    per = {}
    for seed in seeds:
        scen = kit_buyers.make_scenarios(store, policy, n, seed, buyer_classes)
        rows, _, _ = evaluate.run(seller_cls, scen, buyer_classes, store, policy)
        for r in rows:
            per.setdefault(r["buyer"], []).append(r)
    out = {b: evaluate.summarise(rs) for b, rs in per.items()}
    allrows = [r for rs in per.values() for r in rs]
    return out, evaluate.summarise(allrows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--n", type=int, default=210)
    ap.add_argument("--grid", default="{}")
    ap.add_argument("--buyers", nargs="+", default=[None], help="modules with BUYERS ('kit' = kit bots)")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()
    store, policy = load_store(), load_policy()
    buyer_classes = {}
    for spec in args.buyers:
        buyer_classes.update(evaluate.load_buyers(None if spec in (None, "kit") else spec))
    base_by, base_all = score(evaluate.load_class(str(ROOT / "kit/example_seller.py"), "Seller"),
                              buyer_classes, args.seeds, args.n, store, policy)
    print("baseline  mean %.1f  " % base_all["score"] + "  ".join(f"{b} {s['score']:.1f}" for b, s in base_by.items()))
    grid = json.loads(args.grid)
    keys = list(grid)
    res = []
    for combo in itertools.product(*[grid[k] for k in keys]):
        prm = dict(zip(keys, combo))
        by, al = score(seller_with(prm), buyer_classes, args.seeds, args.n, store, policy)
        worst = min(s["score"] - base_by[b]["score"] for b, s in by.items())
        res.append((worst, al["score"], prm, {b: round(s["score"], 1) for b, s in by.items()},
                    al["policy"] + al["truth"], al["deadlocks"]))
    res.sort(key=lambda t: (-t[0], -t[1]))
    print("worst-vs-base  mean   viol dead  params  per-group")
    for w, m, prm, by, v, d in res[:args.top]:
        print(f"{w:+7.1f}  {m:6.1f}  {v:4} {d:4}  {json.dumps(prm)}  {by}")


if __name__ == "__main__":
    main()
