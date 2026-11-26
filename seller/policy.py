"""Store policy: per-unit floors and caps, and a compliance check that mirrors harness.check_items."""
import math


class Policy:
    def __init__(self, store, policy):
        self.store, self.policy = store, policy
        self._floor = {}
        for sku, row in store.items():
            try:
                margin = policy["min_margin"][row["category"]]
                self._floor[sku] = math.ceil(max(row["cost"] / (1 - margin),
                                                 row["price"] * (1 - policy["max_discount"])))
            except (KeyError, TypeError, ZeroDivisionError):
                self._floor[sku] = None            # unknown category: never sell it

    def sellable(self, sku):
        row = self.store.get(sku)
        f = self._floor.get(sku)
        return row is not None and row["stock"] > 0 and f is not None and f <= row["price"]

    def floor(self, sku):
        return self._floor[sku]

    def list_price(self, sku):
        return self.store[sku]["price"]

    def stock(self, sku):
        return self.store[sku]["stock"]

    def cost(self, sku):
        return self.store[sku]["cost"]

    def line_ok(self, sku, qty, price):
        row = self.store.get(sku)
        if row is None or self._floor.get(sku) is None:
            return False
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1 or qty > row["stock"]:
            return False
        if not isinstance(price, (int, float)) or isinstance(price, bool) or price != price:
            return False
        margin = self.policy["min_margin"][row["category"]]
        return (price >= row["cost"] / (1 - margin) and price >= row["price"] * (1 - self.policy["max_discount"])
                and price <= row["price"])

    def compliant(self, items):
        """True only if every line is a well-formed dict that passes every policy rule (as the harness checks)."""
        if not isinstance(items, list) or not items:
            return False
        for it in items:
            if not isinstance(it, dict):
                return False
            if not self.line_ok(it.get("sku"), it.get("qty"), it.get("unit_price")):
                return False
        return True

    def profit(self, items):
        return sum(it["qty"] * (it["unit_price"] - self.cost(it["sku"])) for it in items)
