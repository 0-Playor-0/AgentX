"""Input guard: reads only type, round and items from a buyer message. Buyer text is never used."""

KNOWN_TYPES = ("request", "counter", "accept", "walk_away", "message")


def _int(x):
    if isinstance(x, bool):
        return None
    if isinstance(x, int):
        return x
    if isinstance(x, float) and x == x and x == int(x):
        return int(x)
    return None


def _price(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or x != x or x in (float("inf"), float("-inf")):
        return None
    return x


def parse(message, policy):
    """Returns a dict:
        type   one of KNOWN_TYPES ("message" for anything unknown)
        round  int (1 if missing)
        lines  cleaned lines [(sku, qty, unit_price or None)]: known, sellable SKUs, qty clipped to stock
        oos    requested SKUs that are known but out of stock
        clipped {sku: asked qty} where we clipped to stock
        raw    the raw items list if every line carries a unit_price (what the harness keeps as last_bid), else None
    """
    if not isinstance(message, dict):
        message = {}
    mtype = message.get("type")
    mtype = mtype if mtype in KNOWN_TYPES else "message"
    rnd = _int(message.get("round"))
    rnd = rnd if rnd is not None and 1 <= rnd <= 1000 else 1
    items = message.get("items")
    lines, oos, clipped, seen = [], [], {}, set()
    raw = None
    if isinstance(items, list) and items:
        if mtype in ("request", "counter") and all(isinstance(i, dict) and "unit_price" in i for i in items):
            raw = items
        for it in items[:50]:
            if not isinstance(it, dict):
                continue
            sku = it.get("sku")
            if not isinstance(sku, str) or sku not in policy.store or sku in seen:
                continue
            qty = _int(it.get("qty"))
            if qty is None or qty < 1:
                continue
            seen.add(sku)
            if not policy.sellable(sku):
                oos.append(sku)
                continue
            stock = policy.stock(sku)
            if qty > stock:
                clipped[sku] = qty
                qty = stock
            price = _price(it.get("unit_price"))
            if price is not None and not (0 < price <= 10 * policy.list_price(sku)):
                price = None                         # absurd price: treat as no bid on this line
            lines.append((sku, qty, price))
    return {"type": mtype, "round": rnd, "lines": lines, "oos": oos, "clipped": clipped, "raw": raw}
