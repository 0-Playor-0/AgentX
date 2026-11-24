"""Buyer model from behaviour only: the buyer's bids, as a share of list price on our current basket."""


class BuyerModel:
    def __init__(self):
        self.bids = []            # (round, share of list on our basket)

    def record(self, rnd, share):
        self.bids.append((rnd, share))

    def last(self):
        return self.bids[-1][1] if self.bids else None

    def move(self):
        """Change between the last two bids (share of list), or None."""
        return self.bids[-1][1] - self.bids[-2][1] if len(self.bids) >= 2 else None

    def stalled(self, n, eps=0.002):
        """True if the last n moves were all below eps."""
        if len(self.bids) < n + 1:
            return False
        tail = [b for _, b in self.bids[-(n + 1):]]
        return max(tail) - min(tail) < eps

    def early_speed(self, k=2):
        """Mean move per round over the buyer's first k moves (share of list), or None."""
        if len(self.bids) < k + 1:
            return None
        return (self.bids[k][1] - self.bids[0][1]) / k

    def projected(self, ahead=1):
        """Linear extrapolation of the buyer's bid (share of list) `ahead` rounds on."""
        if not self.bids:
            return None
        m = self.move()
        return self.bids[-1][1] + max(0.0, m or 0.0) * ahead
