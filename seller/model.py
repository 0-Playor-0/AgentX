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

    def projected(self, ahead=1):
        """Linear extrapolation of the buyer's bid (share of list) `ahead` rounds on."""
        if not self.bids:
            return None
        m = self.move()
        return self.bids[-1][1] + max(0.0, m or 0.0) * ahead
