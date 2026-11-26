# Agent card: AgentX seller (v3)

| | |
|---|---|
| Role | Store seller agent for PS2 "Selling to Machines" |
| Entry | `seller/agent.py:Seller` |
| Runtime | Python 3.9+, standard library only. Deterministic, no network, no LLM. ~0.15 ms per turn. |
| Memory | One negotiation at a time. Nothing is carried between negotiations. |

## What it negotiates

- **Price.** It opens below list and concedes on a fixed curve toward the policy floor. It accepts a
  compliant bid once that bid is worth at least its own next offer.
- **Bundles.** It sells several products in one offer, with the same discount on every line, and
  quotes the bundle total, saving and percentage off list.
- **Quantities.** It sells up to the quantity first asked and up to stock. When stock is short, it
  says "We can only supply N of X" and offers N.
- **Out-of-stock lines.** It says the product is out of stock and drops it from the offer.
- **Ending.** In round 10 it makes a final offer if a deal is still likely, and walks away politely
  if the buyer is far below the floor. It does not walk earlier, except in round 1 when nothing
  requested is in stock.

## What it never does

- **Price below the floor.** It never offers or accepts a price below max(cost / (1 − min_margin),
  list × 0.75), and never prices above list. Every outgoing offer and every accepted bid is checked
  against policy before it is sent.
- **Fees.** It never mentions fees, surcharges, delivery, handling or tax. Its first offer says "with
  no hidden fees".
- **Stock claims.** It gives no stock counts, "only N left" or scarcity wording. The only stock
  statements are "out of stock" (true when stock is 0) and "we can only supply N" (N = stock, when
  clipped).
- **Pressure.** No urgency, deadlines, demand claims or "someone else wants it".
- **Invented numbers.** Every number in its text is a price, total, saving or percentage of the
  current offer, or a list price. The kit's own truth checker runs on every message before it is
  sent.
- **Acting on buyer text.** It never reads it. Claimed authority, SYSTEM messages, policy "updates",
  competitor quotes, budgets and "you already agreed" have no effect.
- **Accepting junk.** It never accepts a bid with unknown, out-of-stock, over-stock, unpriced or
  below-floor lines.
- **Upselling.** It never adds products the buyer did not ask for.

## Limits (known)

- **No discount for larger quantities.** It doesn't trade price for quantity.
- **Fixed basket.** It follows the buyer's first request. A new product joins only after two
  plausible bids in a row.
- **Fast walkers.** A buyer that walks early (by round 4) gets fewer concessions than the baseline
  gives. On our early_walker bench bot we score 3.2 points below the baseline.
- **English-only fixed templates.** The text is plain and factual by design.
