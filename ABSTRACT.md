# Problem Statement 2: Selling to Machines

**A seller agent that cannot be talked out of its policy**

**Impact.** Shoppers now send AI agents to buy for them. These buyers bargain tirelessly,
invent competitor quotes and slip in "SYSTEM" or "store manager" instructions. A language-model seller
can be argued below cost or make a false claim. Ours closes more profitable deals than the kit baseline
and cannot break policy or say anything false, whatever the buyer writes.

**Innovation.** The seller never reads the buyer's text. A deal is defined only by the structured
items, so the seller negotiates on behaviour: what the buyer bids, and how those bids move. Injection,
fake authority and invented quotes have nothing to act on.
- **Pricing.** It uses one unit per basket, from the policy floor (0) to list price (1). One
  concession curve covers single items and bundles, with an equal discount on every line.
- **Acceptance (AC_next).** It takes a bid once the bid is worth at least its own next offer.
- **Round 10.** An expected-value rule on the buyer's projected bid chooses between a final offer and
  walking away. This avoids deadlocks without losing closable deals.
- **Text.** Fixed templates, numbered from the current offer. Each message passes the competition's
  truth checker and a policy check before sending, with a safe fallback.

**Method.** Robustness over peak score.
- **Sweep.** On the three kit bots and seven adversarial rule buyers of ours, over 5 seeds, we took
  the centre of the region beating the baseline on every group, not the best point.
- **Fewer knobs.** Four parameters remain.
- **LLM buyers** only validated, never tuned.
- **Held-out test.** A final test ran once, after freezing, on unseen buyer styles and a different
  model. An earlier version failed it by conceding too fast to LLM buyers, which led to AC_next.

**Results.**
- **Kit evaluation:** 52.2 vs the baseline's 48.5, ahead on all three bots. 0 policy and 0 truth
  violations; 2 deadlocks against the baseline's 21.
- **Ten-group bench:** 40.5 vs 36.4, ahead on nine groups. The exception is a buyer that leaves by
  round 4 (−3.2).
- **Held-out LLM buyers** (gpt-oss-120b, 32 negotiations, 0 fallbacks): 57.5 vs 54.0, ahead on three
  of four personas, 0 violations, 0 deadlocks. It failed our own gate on llm_hard (−7.3, n = 8): one
  buyer walked away in round 6, the known early-walker limit. No parameters were retuned.
- **Red team:** replaying every logged negotiation with all buyer text blanked changes 0 of 1,626
  decisions.

**Cost.** No model calls, GPU or network: 949 negotiations per second on one CPU core, about $0.013 per
million negotiations. A GPT-5 mini seller would cost about $6,200 per million (2,000 input and 200
output tokens per turn, list prices). Deterministic: every negotiation replays exactly.

**Build.** About 630 lines of standard-library Python, including a log-only reason trace.
- **Tests:** 600 fuzzed negotiations through the official harness, and 1,500 negotiations of
  malformed JSON sent straight to the seller.
