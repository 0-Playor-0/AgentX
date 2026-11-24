"""Templates for the seller's text. Numbers come only from the current offer: unit prices, line totals,
basket total, list total, saving vs list and its percentage. No stock counts, urgency, scarcity or fee words."""


def _names(items, store):
    parts = [f"{i['qty']} x {store[i['sku']]['name']}" if i["qty"] > 1 else store[i["sku"]]["name"] for i in items]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _sum(items, store):
    total = sum(i["qty"] * i["unit_price"] for i in items)
    listed = sum(i["qty"] * store[i["sku"]]["price"] for i in items)
    return total, listed


def notes(store, oos, clipped, basket):
    """Truthful notes about what we can't fully supply (no stock numbers)."""
    out = []
    for sku in oos:
        out.append(f"Sorry, {store[sku]['name']} is out of stock.")
    qty = dict(basket)
    for sku in clipped:
        if sku in qty:
            out.append(f"We can only supply {qty[sku]} of {store[sku]['name']}, so this offer is for {qty[sku]}.")
    return " ".join(out)


def clip_note(store, clipped, basket):
    qty = dict(basket)
    return " ".join(f"We can only supply {qty[s]} of {store[s]['name']}." for s in clipped if s in qty)


def offer_text(items, store, mode, first, at_floor, prefix=""):
    total, listed = _sum(items, store)
    saving = listed - total
    names = _names(items, store)
    bundle = len(items) > 1
    pct = int(round(100 * saving / listed)) if listed else 0
    if mode == "plain":
        body = f"I can do {names} for ₹{total:,}."
    else:
        if saving <= 0:
            body = f"{names} come{'s' if not bundle and items[0]['qty'] == 1 else ''} to ₹{total:,} at list price."
        elif at_floor:
            body = (f"₹{total:,} for {names} is the best price our policy allows: ₹{saving:,} off the list "
                    f"price of ₹{listed:,}, with no hidden fees.")
        elif first:
            body = (f"For {names} the list price is ₹{listed:,}; I can offer ₹{total:,}"
                    f"{' as a bundle' if bundle else ''}, with no hidden fees.")
        else:
            body = (f"I've come down to ₹{total:,} for {names}{' as a bundle' if bundle else ''}: "
                    f"₹{saving:,} ({pct}%) off the list price of ₹{listed:,}.")
    return (prefix + " " + body).strip()


SAFE_OFFER = "Here is our offer."
ACCEPT = "Deal, thank you!"
WALK = "I'm sorry, we can't meet that price within our pricing policy. Thank you for your time."
NOTHING = "Sorry, we can't supply any of the items requested."
ASK = "Which products would you like, and how many?"
