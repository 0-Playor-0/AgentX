# AgentX PS2 — Selling to Machines

Seller agent for Techfest IIT Bombay 2026–27, Problem Statement 2. A deterministic, standard-library
seller that negotiates price and bundles with buyer bots, never breaks store policy, and never says
anything the store's data doesn't support.

- `seller/`: the seller (entry `seller/agent.py:Seller`). See [ARCHITECTURE.md](ARCHITECTURE.md) and
  [AGENT_CARD.md](AGENT_CARD.md).
- `kit/`: the official starter kit, unmodified. Re-download it before the final run.
- `bench/`: rule-based and LLM test buyers, sweeps and results (`bench/results/`).
- `demo/replay.html`: the demo-video viewer (single self-contained file, works from `file://`): three
  story replays (chat, live price chart, controls) and a results card. Every number comes from the logs:
  ```
  python kit/evaluate.py --seller seller/agent.py --log logs/transcripts.jsonl
  python kit/evaluate.py --log logs/baseline.jsonl
  python demo/build_replay.py logs/transcripts.jsonl --baseline logs/baseline.jsonl [--heldout bench/results/heldout2_oss_s600.jsonl]
  ```
  Each seller turn shows a **Why:** line: the seller's own reason trace (rule + numbers). The seller
  keeps it in memory only (`Seller.trace`), never sends it to the buyer;
  `python demo/why_trace.py logs/transcripts.jsonl` rebuilds `logs/why.jsonl` by replaying the log and
  checks every replayed decision against it.
  Keys: Space play/pause, ←/→ step, F fullscreen, Esc back. Deep links: `#story=neg-009&step=end`,
  `#view=results`. Screenshots at 1920×1080: `demo/screenshots/`.
- [docs/REDTEAM.md](docs/REDTEAM.md): every manipulation attempt in the logs by type, and how many changed
  a seller decision (0 of 1,626 decisions, by replaying each negotiation with all buyer text blanked).
  Rebuild with `python bench/redteam.py`.
- `tests/`: property tests and fuzzing. Run with `python -m unittest discover -s tests`.

```
python kit/evaluate.py                                                          # baseline
python kit/evaluate.py --seller seller/agent.py --log logs/transcripts.jsonl    # ours
python bench/run_bench.py --set rule --n-per 20                                 # our rule buyers vs baseline
```

LLM test buyers need `GROQ_API_KEY` or `GEMINI_API_KEY` (an environment variable, or `.env`; see
`.env.example`).

## Results (v3, frozen)

### Kit evaluation, default run (`python kit/evaluate.py --seller seller/agent.py`, 210 negotiations)

| buyer | n | ours | baseline | diff |
|---|---|---|---|---|
| cooperative | 70 | 72.3 | 69.1 | +3.2 |
| hard_bargainer | 70 | 44.6 | 40.8 | +3.8 |
| manipulator | 70 | 39.7 | 35.5 | +4.2 |
| **total** | 210 | **52.2** | **48.5** | **+3.7** |

- Violations: 0 policy and 0 truth, for both us and the baseline.
- Deadlocks: 2 for us, 21 for the baseline.
- Latency: 0.15 ms per turn (p95 0.22 ms). Throughput: 949 negotiations/s on one core (see Cost below).

### Cost and throughput

Measured with `taskset -c 0 python bench/speed.py` (one core, Intel Xeon @ 2.1 GHz, Python 3.13; the kit's
210 scenarios played 5 times, single-threaded):

- **Seller only:** 949 negotiations/s (0.153 ms per turn, 6.9 seller turns per negotiation).
- **End to end:** 462 negotiations/s, including the kit buyer bots and the harness's checks.

Cost per 1M negotiations (estimates; the assumptions are listed below the table):

| seller | compute per 1M negotiations | cost per 1M negotiations |
|---|---|---|
| **Ours** (deterministic, no model calls) | 0.29 core-hours | **≈ $0.013** |
| LLM seller, gpt-oss-120b on Groq | 13.8B input + 1.38B output tokens | ≈ $3,100 |
| LLM seller, GPT-5 mini (OpenAI) | 13.8B input + 1.38B output tokens | ≈ $6,200 |

- **Ours:** 1M ÷ 949/s = 1,054 core-seconds, at $0.0446 per vCPU-hour (AWS EC2 c7i.large on-demand,
  us-east-1, $0.0893/h for 2 vCPUs; [aws.amazon.com/ec2/pricing/on-demand](https://aws.amazon.com/ec2/pricing/on-demand/)).
- **LLM seller:** 6.9 turns per negotiation (as measured for ours). Each turn sends about 2,000 input tokens
  (system prompt, policy, the basket's catalogue rows and the transcript so far) and gets about 200 output
  tokens back (the JSON offer and message). No reasoning tokens, caching or batch discounts are counted.
  - gpt-oss-120b on Groq: $0.15 per 1M input and $0.75 per 1M output tokens
    ([groq.com launch post](https://groq.com/blog/day-zero-support-for-openai-open-models); some trackers
    list $0.60 output, which gives ≈ $2,900).
  - GPT-5 mini: $0.25 per 1M input and $2.00 per 1M output tokens ([openai.com/api/pricing](https://openai.com/api/pricing/)).
- Prices were checked on 27 Nov 2026.
- On these assumptions an LLM seller costs about 200,000× more per negotiation than ours, before
  counting its latency or its exposure to the manipulation in [docs/REDTEAM.md](docs/REDTEAM.md).

### Kit + rule buyers, 5 seeds (the parameter-selection bench)

| group | ours | baseline | diff |
|---|---|---|---|
| cooperative | 68.5 | 65.4 | +3.1 |
| hard_bargainer | 41.8 | 39.4 | +2.4 |
| manipulator | 40.4 | 35.9 | +4.5 |
| step_conceder | 52.9 | 50.9 | +2.0 |
| early_walker | 39.3 | 42.5 | **−3.2** |
| never_leaver | 35.6 | 21.9 | +13.6 |
| injector | 42.7 | 39.3 | +3.3 |
| junk_lines | 35.9 | 34.5 | +1.4 |
| bundle_demander | 40.9 | 35.6 | +5.4 |
| below_floor | 7.1 | −1.2 | +8.3 |
| **mean** | **40.5** | **36.4** | **+4.1** |

- Violations: 0. Source: `bench/results/v3_robust_B_0.8_0.8.{txt,json}`.
- early_walker is the one accepted exception. It walks by round 4, before our curve has conceded much.

### Held-out LLM buyers (gpt-oss-120b via Groq, seed 600, run once after freezing)

Thinking off, except for llm_manipulator. 4 personas × 8 negotiations = 32, each played by both sellers
against the same cached buyer replies. 388 LLM buyer replies: 0 fallbacks, 0 API errors, 0 bad JSON.

Gate (set before the run): overall ≥ baseline and no persona worse than −5.

| persona | n | ours | baseline | diff |
|---|---|---|---|---|
| ho2_budget_swinger (unseen) | 8 | 71.0 | 58.5 | +12.5 |
| ho2_splitter (unseen) | 8 | 45.8 | 38.5 | +7.3 |
| llm_hard | 8 | 46.9 | 54.3 | **−7.3** |
| llm_manipulator | 8 | 66.4 | 64.9 | +1.5 |
| **overall** | 32 | **57.5** | **54.0** | **+3.5** |

- Violations: 0 policy and 0 truth, for both. Deadlocks: 0 for both. Deals: 25 each.
- **The gate failed** on llm_hard (−7.3, past −5); overall passed. The whole gap is one negotiation
  (neg-019): the buyer walked away in round 6, before our curve had conceded enough, while the baseline
  closed it (66.9 → −8.4 on the mean of 8). This is the known early-walker limit (see early_walker
  above), not a bug. Per our pre-committed rule, v3 ships unchanged: no parameters were changed from
  held-out results. With n = 8 per persona, these differences are noisy.
- Source: `bench/results/heldout2_oss_s600.{txt,jsonl}`.
