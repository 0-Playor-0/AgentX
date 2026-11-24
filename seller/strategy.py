"""Concession strategy. Works in x, the share of the floor-to-list range: x = 0 is the floor total, 1 the list total.

Parameters are FROZEN (v3: AC_next acceptance, no fast-buyer mode): chosen on kit + rule buyers (5 seeds) as the centre of the region where we are >= baseline
on every group (see bench/robust.py and bench/results/robust_*.json). LLM buyers are validation only.
"""

DEFAULTS = {
    "x0": 0.8,            # opening offer (x units; 1 = list price)
    "e": 1.0,             # curve exponent: x(r) = x0 * (1 - ((r-1)/(R-1))^e)
    "stall_step": 0.05,   # one test concession (in x) after the buyer's bid is unchanged for 2 rounds
    "final_k": 0.5,       # last round: offer at this fraction of the buyer's projected bid above floor (0 = floor)
    "walk_gap": 0.05,     # last round: walk if the buyer's projected bid is more than this (share of list) below floor
}


def curve(r, R, e):
    if R <= 1:
        return 0.0
    t = min(1.0, max(0.0, (r - 1) / (R - 1)))
    return 1.0 - t ** e
