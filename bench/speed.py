"""Throughput on one CPU core: negotiations per second, seller only and end to end.

    taskset -c 0 python bench/speed.py [--reps 5]

Plays the kit evaluation's 210 scenarios (seed 0) with the kit buyer bots, single-threaded.
Seller-only = negotiations / total time inside Seller.respond (the evaluator's own Timed wrapper).
End to end = negotiations / wall time, including the kit buyer bots and the harness's checks.
"""
import argparse
import os
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "kit"))
sys.path.insert(0, str(ROOT))

import buyers                                    # noqa: E402
import evaluate                                  # noqa: E402
from harness import load_policy, load_store      # noqa: E402
from seller.agent import Seller                  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--reps", type=int, default=5)
    args = ap.parse_args()
    store, policy = load_store(), load_policy()
    scenarios = buyers.make_scenarios(store, policy, 210, 0, buyers.BUYERS)
    n = seller_t = wall = turns = 0
    for _ in range(args.reps):
        t0 = time.perf_counter()
        _, _, times = evaluate.run(Seller, scenarios, buyers.BUYERS, store, policy, workers=1)
        wall += time.perf_counter() - t0
        seller_t += sum(times)
        turns += len(times)
        n += len(scenarios)
    cores = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else "?"
    print(f"cpu: {platform.processor() or platform.machine()}, python {platform.python_version()}, cores allowed: {cores}")
    print(f"{n} negotiations, {turns} seller turns ({turns / n:.1f} per negotiation)")
    print(f"seller only : {n / seller_t:,.0f} negotiations/s  ({1000 * seller_t / turns:.3f} ms per turn)")
    print(f"end to end  : {n / wall:,.0f} negotiations/s  (kit buyer bots + harness checks included)")


if __name__ == "__main__":
    main()
