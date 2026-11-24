# Architecture

A deterministic seller in ~530 lines of standard-library Python. No LLM, no network, no state between
negotiations. Entry point: `seller/agent.py:Seller`.

## Pipeline (one buyer message in, one seller message out)

```
 buyer message (JSON)
        │
        ▼
 ┌─────────────┐  type, round, items only. Unknown/duplicate SKUs, bad qty and junk prices dropped;
 │  guard      │  qty clipped to stock; out-of-stock SKUs noted. The `text` field is never read.
 └─────┬───────┘
       ▼
 ┌─────────────┐  per-SKU floor = max(cost / (1 − min_margin), list × 0.75), list, stock;
 │  policy     │  the same compliance check the harness runs (used again at the exit gate).
 └─────┬───────┘
       ▼
 ┌─────────────┐  the buyer's bids on our basket as a share of list price; last move; projected next bid.
 │  model      │  Built from behaviour (numbers) only.
 └─────┬───────┘
       ▼
 ┌─────────────┐  concession curve in x-space (0 = floor total, 1 = list total); AC_next acceptance;
 │  strategy   │  round-10 EV rule. One x for the whole basket = an equal bundle discount on every line.
 └─────┬───────┘
       ▼
 ┌─────────────┐  fixed templates. Numbers only from the current offer (unit price, totals, saving, %).
 │  writer     │  No stock counts, urgency, scarcity or fee words.
 └─────┬───────┘
       ▼
 ┌─────────────┐  the kit's own `check_text` (vendored verbatim) run on our text before sending; plus a
 │  selfcheck  │  final policy check on the items. On any failure: a safe fixed text / last valid offer.
 └─────┬───────┘
       ▼
 seller message (always a valid dict, even on an internal exception)
```

## Decisions

**Concession curve.** Offer x(r) = x0 · (1 − ((r−1)/(R−1))^e) with x0 = 0.8, e = 0.8, R = 10.
Never offer less than the buyer is currently bidding, and never raise our price.

**AC_next acceptance.** Accept a compliant bid when its profit is at least the profit of the offer we
would make next round. In round 10, accept any compliant bid.

**Round-10 EV rule.** In the last round the buyer either takes our offer or the negotiation ends.
Project the buyer's next bid (last bid + its last upward move).
- If the projected bid is more than 5% of list below the floor, walk. A deal is unlikely, and a
  deadlock costs −0.25.
- Otherwise offer halfway between the floor and the projected bid (in x-space). This trades a little
  margin for a higher chance of closing.

The bench checks the gate: our round-10 offers must have positive mean outcome.

**Basket.** Fixed from the buyer's first request.
- Quantities are capped at what was first asked, so later "make it 28" lines are ignored.
- A new SKU joins only if the buyer bids at least 50% of its list price in two consecutive bids. A
  ₹1 slip-in never joins.

**Why buyer text is ignored.** The text is where the manipulation lives: fake SYSTEM and "store
manager" orders, fake competitor quotes and budgets, "you already agreed". The deal itself is defined
only by `items`. Reading text could only make us easier to manipulate, so the guard never passes it on.
The one place text matters is our own output, and that is checked with the harness's checker before
sending.

## How the parameters were chosen (robustness over peak score)

1. **Sweep on rule-based buyers only.** The 3 kit bots plus 7 of our own: step_conceder,
   early_walker, never_leaver, injector, junk_lines, bundle_demander and below_floor. 5 seeds each.
2. **Admissibility.** A point must be at or above the kit baseline on every group. early_walker is the
   one reported exception, at −3.2.
3. **Choice.** Take the centre of the flat admissible region, not the argmax, scoring each point by
   the worst mean over itself and its grid neighbours. No single bot drives a choice.
   - Knobs the sweep set to 0 were deleted: reciprocity, fast-buyer mode and the stall step.
   - Four parameters remain.
4. **LLM buyers are validation only.** Nothing is tuned on them; there are too few samples.
5. **Held-out check.** A fresh seed, unseen buyer styles and a second model (gpt-oss-120b, thinking
   on), run once after freezing.
   - Gate: overall ≥ baseline and no persona worse than −5.
   - v2 failed it. Its fast-buyer mode over-conceded to LLM buyers, which led to v3: AC_next and no
     fast mode.

Tests: `python -m unittest discover -s tests`.
- 600 fuzz negotiations through the harness.
- 1,500 negotiations of arbitrary JSON sent straight into `respond()`.
- The kit bots.
- A determinism check.
- A check that the vendored checker matches the kit's.
