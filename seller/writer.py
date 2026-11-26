"""Templates for the seller's text. Numbers come only from the current offer: unit prices, line totals,
basket total, list total, saving vs list and its percentage. No stock counts, urgency, scarcity or fee words."""


def name(store, sku):
    """'Pacevo Slim Fit T-Shirt, Green' -> 'Pacevo Slim Fit T-Shirt (Green)', so ' and ' joins read cleanly."""
    base, sep, colour = store[sku]["name"].rpartition(", ")
    return f"{base} ({colour})" if sep and base else store[sku]["name"]


def _names(items, store):
    parts = [f"{i['qty']} x {name(store, i['sku'])}" if i["qty"] > 1 else name(store, i["sku"]) for i in items]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _sum(items, store):
    total = sum(i["qty"] * i["unit_price"] for i in items)
    listed = sum(i["qty"] * store[i["sku"]]["price"] for i in items)
    return total, listed


def notes(store, oos, clipped, basket):
    """Truthful notes about what we can't fully supply (no stock numbers)."""
    out = []
    for sku in oos:
        out.append(f"Sorry, {name(store, sku)} is out of stock.")
    qty = dict(basket)
    for sku in clipped:
        if sku in qty:
            out.append(f"We can only supply {qty[sku]} of {name(store, sku)}, so this offer is for {qty[sku]}.")
    return " ".join(out)


def clip_note(store, clipped, basket):
    qty = dict(basket)
    return " ".join(f"We can only supply {qty[s]} of {name(store, s)}." for s in clipped if s in qty)


def offer_text(items, store, first, at_floor, prefix=""):
    total, listed = _sum(items, store)
    saving = listed - total
    names = _names(items, store)
    bundle = len(items) > 1
    pct = int(round(100 * saving / listed)) if listed else 0
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
ACCEPT = "Deal, thank you!"          # also the self-check fallback for accept_text
THANKS = "Thank you for your time."


def accept_text(items):
    """'Deal at ₹{buyer's total}, thank you!' (the bid's total is in play for the truth checker)."""
    try:
        total = sum(i["qty"] * i["unit_price"] for i in items)
    except Exception:
        return ACCEPT
    if not isinstance(total, (int, float)) or total != int(total) or total <= 0:
        return ACCEPT
    return f"Deal at ₹{int(total):,}, thank you!"


def oos_walk(store, oos):
    """Round 1, nothing requested is in stock: the out-of-stock notes, then a polite close."""
    note = notes(store, oos, {}, [])
    return f"{note} {THANKS}" if note else NOTHING
WALK = "I'm sorry, we can't meet that price within our pricing policy. Thank you for your time."
NOTHING = "Sorry, we can't supply any of the items requested."
ASK = "Which products would you like, and how many?"
