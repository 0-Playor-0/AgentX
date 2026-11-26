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
  Keys: Space play/pause, ←/→ step, F fullscreen, Esc back. Deep links: `#story=neg-009&step=end`,
  `#view=results`. Screenshots at 1920×1080: `demo/screenshots/`.
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
- Latency: 0.15 ms per turn (p95 0.22 ms).

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
- **The gate failed** on llm_hard (−7.3, past −5); overall passed. Per our pre-committed rule, v3 ships
  unchanged: no parameters were changed from held-out results. The transcripts show no bug; llm_hard
  loses for the known fast-walker reason (it leaves before our curve has conceded much, as with
  early_walker above). With n = 8 per persona, these differences are noisy.
- Source: `bench/results/heldout2_oss_s600.{txt,jsonl}`.
