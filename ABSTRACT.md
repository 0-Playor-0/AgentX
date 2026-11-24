# Abstract (draft)

**A seller agent that cannot be talked out of its policy**

**Impact.** Shoppers are starting to send AI agents to buy for them. These buyers bargain without
tiring, invent competitor quotes and budgets, and slip in "SYSTEM" or "store manager" instructions. A
seller built on a language model can be argued below cost, or can state a discount or stock claim
that isn't true. Each is a real loss or a legal risk. Our seller closes more profitable deals than
the kit baseline and cannot break policy or say anything false, whatever the buyer writes.

**Innovation.** The seller never reads the buyer's text. A deal is defined only by the structured
items, so the seller negotiates on behaviour: what the buyer bids, and how those bids move. Injection,
fake authority and invented quotes have nothing to act on. It is robust by construction, not by
filtering.
- **Pricing.** It uses one unit per basket, from the policy floor (0) to list price (1). One
  concession curve covers single items and bundles, with an equal discount on every line.
- **Acceptance (AC_next).** It takes a bid once the bid is worth at least its own next offer.
- **Round 10.** An expected-value rule on the buyer's projected bid chooses between a final offer and
  walking away. This avoids deadlocks without giving up deals that can still close.
- **Text.** It comes from fixed templates whose numbers come from the current offer. Each message is
  checked with the competition's own truth checker and a policy check before it is sent, with a safe
  fallback.

**Method.** We chose parameters for robustness, not peak score.
- **Sweep.** On the three kit bots and seven adversarial rule-based buyers of our own, over 5 seeds,
  we took the centre of the region where we beat the baseline on every group, not the single best
  point.
- **Fewer knobs.** Unused features were deleted, leaving four parameters.
- **LLM buyers** were used only to validate, never to tune.
- **Held-out test.** A final test ran once, after freezing, on unseen buyer styles and a different
  model. An earlier version failed it by conceding too fast to LLM buyers, which led to AC_next.

**Results.**
- **Kit evaluation:** 52.2 vs the baseline's 48.5, ahead on all three bots. 0 policy and 0 truth
  violations; 2 deadlocks against the baseline's 21.
- **Ten-group bench:** 40.5 vs 36.4, ahead on nine groups. The exception is a buyer that leaves by
  round 4 (−3.2).
- **Held-out LLM buyers:** _[TBD]_.

**Cost.** ₹0 inference: no model calls, GPU or network. About 0.15 ms per turn on one CPU core,
thousands of times faster than a single LLM call. The seller is deterministic, so every negotiation
can be replayed and audited.

**Build.** About 530 lines of standard-library Python: guard, policy, buyer model, strategy, writer
and self-check.
- **Tests:** 600 fuzzed negotiations through the official harness, and 1,500 negotiations of
  malformed JSON sent straight to the seller.
- **Test bench:** adversarial rule-based buyers and LLM buyer personas.
- **Demo:** a replay page showing injections ignored, a bundle deal and a round-10 walk-away.
