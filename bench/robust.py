"""Robust parameter choice on non-LLM buyers (kit + rule): grid, then pick the centre of the flat region.

For every grid point: per-group score vs baseline over several seeds. A point is admissible if it is >= baseline
on EVERY group. Its robustness is the worst equal-weight mean score over the point and its grid neighbours
(one step along any axis); a neighbour that is not admissible makes the point's robustness -inf. The pick is the
point with the best robustness (the centre of the flat region), not the argmax of the mean.

    python bench/robust.py --grid '{"x0":[...],"e":[...]}' --seeds 0 1 2 3 4 --out bench/results/robust.json
"""
import argparse
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))
sys.path.insert(0, str(ROOT / "kit"))
import evaluate                                           # noqa: E402
from harness import load_class, load_policy, load_store   # noqa: E402
from sweep import score, seller_with                      # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", required=True)
    ap.add_argument("--fixed", default="{}")
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3, 4])
    ap.add_argument("--n", type=int, default=210)
    ap.add_argument("--out")
    args = ap.parse_args()
    store, policy = load_store(), load_policy()
    classes = dict(evaluate.load_buyers(None))
    classes.update(evaluate.load_buyers(str(ROOT / "bench/rule_buyers.py")))
    base_by, _ = score(load_class(str(ROOT / "kit/example_seller.py"), "Seller"), classes, args.seeds, args.n,
                       store, policy)
    grid, fixed = json.loads(args.grid), json.loads(args.fixed)
    keys = list(grid)
    pts = {}
    for idx in itertools.product(*[range(len(grid[k])) for k in keys]):
        prm = dict(fixed, **{k: grid[k][i] for k, i in zip(keys, idx)})
        by, _ = score(seller_with(prm), classes, args.seeds, args.n, store, policy)
        diffs = {b: by[b]["score"] - base_by[b]["score"] for b in by}
        mean = sum(by[b]["score"] for b in by) / len(by)
        viol = sum(by[b]["policy"] + by[b]["truth"] for b in by)
        pts[idx] = {"params": prm, "mean": mean, "worst_diff": min(diffs.values()),
                    "worst_group": min(diffs, key=diffs.get), "diffs": diffs, "viol": viol}
        print(f"{json.dumps(prm)}  mean {mean:.2f}  worst {min(diffs.values()):+.2f} ({min(diffs, key=diffs.get)})",
              flush=True)

    def neighbours(idx):
        yield idx
        for d in range(len(idx)):
            for step in (-1, 1):
                j = list(idx)
                j[d] += step
                if 0 <= j[d] < len(grid[keys[d]]):
                    yield tuple(j)

    for idx, p in pts.items():
        nb = [pts[j] for j in neighbours(idx)]
        p["robust"] = min(q["mean"] for q in nb) if all(q["worst_diff"] >= 0 and q["viol"] == 0 for q in nb) \
            else float("-inf")
    ranked = sorted(pts.values(), key=lambda p: (-p["robust"], -p["mean"]))
    best_mean = max(pts.values(), key=lambda p: p["mean"])
    print("\nbaseline by group:", {b: round(s["score"], 1) for b, s in base_by.items()})
    print("argmax mean:", json.dumps(best_mean["params"]), f"{best_mean['mean']:.2f}",
          f"worst {best_mean['worst_diff']:+.2f} ({best_mean['worst_group']})")
    print("top by robustness (centre of flat region):")
    for p in ranked[:8]:
        print(f"  robust {p['robust']:6.2f}  mean {p['mean']:6.2f}  worst {p['worst_diff']:+5.2f} ({p['worst_group']})  "
              f"{json.dumps(p['params'])}")
    adm = sum(p["worst_diff"] >= 0 for p in pts.values())
    print(f"admissible (>= baseline on every group): {adm}/{len(pts)}")
    if args.out:
        Path(args.out).write_text(json.dumps({"grid": grid, "fixed": fixed, "seeds": args.seeds,
                                              "baseline": {b: s["score"] for b, s in base_by.items()},
                                              "points": [dict(p, idx=list(i)) for i, p in pts.items()]}, indent=1))


if __name__ == "__main__":
    main()
