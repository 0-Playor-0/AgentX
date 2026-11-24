"""Concession strategy. Works in x, the share of the floor-to-list range: x = 0 is the floor total, 1 the list total."""

DEFAULTS = {
    "x0": 0.8,           # opening offer (x units; 1 = list price)
    "e": 1.0,            # Boulware exponent: x(r) = 1 - ((r-1)/(R-1))^e; e > 1 holds high early
    "recip": 0.0,        # reciprocity: concede this fraction of the buyer's upward move (in x units)
    "stall_step": 0.05,  # one test concession (in x) after the buyer stalls for 2 rounds
    "fast_speed": 0.03,  # buyer's early mean move per round (share of list) that marks a fast/impatient buyer
    "fast_R": 7,         # in fast mode the curve reaches the floor by this round instead of R
    "late": 10,          # from this round on, accept any compliant bid
    "walk_gap": 0.03,    # last round: walk if the buyer's last bid is more than this (share of list) below floor
    "final_k": 0.5,      # last round: offer at this fraction of the buyer's projected bid above floor (0 = floor)
    "mode": "persuasive",
}


def curve(r, R, e):
    if R <= 1:
        return 0.0
    t = min(1.0, max(0.0, (r - 1) / (R - 1)))
    return 1.0 - t ** e
