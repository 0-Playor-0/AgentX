# Architecture

Deterministic seller, ~630 lines of standard-library Python: no LLM, no network, no state between
negotiations, 949 negotiations/s on one core. Entry: `seller/agent.py:Seller`.

## Pipeline: one buyer message in, one seller message out

```
  buyer message (JSON)
        ▼
 ┌─────────────┐
 │ guard       │  Reads type, round, items only; buyer text is never read. Drops unknown or
 ├─────────────┤  duplicate SKUs, bad qty, junk prices; clips qty to stock; notes out-of-stock.
 │ policy      │  Per-SKU floor = max(cost / (1 − min_margin), list × 0.75); the harness's own
 ├─────────────┤  compliance check, used again at the exit gate.
 │ model       │  Buyer's bids on our basket as a share of list; last move; projected next bid.
 ├─────────────┤  Numbers only.
 │ strategy    │  Concession curve in x (0 = floor total, 1 = list total); AC_next; round-10 EV
 ├─────────────┤  rule. One x per basket = the same discount on every bundle line.
 │ writer      │  Fixed templates; numbers only from the current offer. No stock counts,
 ├─────────────┤  urgency, scarcity or fee words.
 │ selfcheck   │  Kit's check_text (vendored verbatim) on our text, policy check on our items.
 └─────────────┘  Any failure: safe fixed text / last valid offer.
        ▼
  seller message (always a valid dict)          + one "why" line in Seller.trace (log only)
```

## Decisions

**Curve.** x(r) = x0 · (1 − ((r−1)/(R−1))^e), x0 = 0.8, e = 0.8, R = 10. Never below the buyer's bid;
never raise our price.

**AC_next.** Accept a compliant bid whose profit ≥ that of our next offer; in round 10, any compliant bid.

**Round-10 EV rule.** Project the next bid (last bid + last upward move). More than 5% of list below
the floor: walk (a deadlock costs −0.25). Otherwise offer halfway from the floor to the projected bid.

**Basket.** Fixed by the first request; qty capped at the first ask. A new SKU joins only after two
bids in a row at ≥ 50% of list, so a ₹1 slip-in never joins.

**Buyer text is ignored** because that is where manipulation lives; a deal is defined only by `items`.
Blanking all buyer text changes 0 of 1,626 logged decisions ([docs/REDTEAM.md](docs/REDTEAM.md)).

## Parameter choice: robustness over peak score

1. **Sweep** on rule buyers only: 3 kit bots + 7 of ours, 5 seeds each.
2. **Admissible:** ≥ baseline on every group (one reported exception: early_walker, −3.2).
3. **Choice:** centre of the flat admissible region, not the argmax. Knobs swept to 0 were deleted;
   four parameters remain.
4. **LLM buyers** validate only; nothing is tuned on them.
5. **Held-out,** run once after freezing (gpt-oss-120b, unseen personas). Gate: overall ≥ baseline,
   no persona below −5. v2 failed, which led to v3. v3: 57.5 vs 54.0, but llm_hard −7.3 (one buyer
   left in round 6); shipped unchanged, as pre-committed.

**Tests:** 600 fuzz negotiations through the harness, 1,500 of arbitrary JSON into `respond()`, the kit
bots, determinism, and vendored checker = kit's.
