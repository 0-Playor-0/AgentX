# AgentX PS2 — Selling to Machines

Seller agent for Techfest IIT Bombay 2026–27, Problem Statement 2.

- `kit/` — official starter kit, unmodified (re-download before the final run).
- `seller/` — our seller (deterministic, std-lib only; entry `seller/agent.py:Seller`). *(v1)*
- `bench/` — extra rule-based and LLM buyers for testing. *(in progress)*
- `HANDOFF_01_agentx.md` — plan and decisions.

```
python kit/evaluate.py                                   # baseline (48.5)
python kit/evaluate.py --seller seller/agent.py --log logs/transcripts.jsonl
```

LLM test buyers need `GEMINI_API_KEY` (environment variable, or `.env` — see `.env.example`).

## Status (v1, kit bots, default run `python kit/evaluate.py --seller seller/agent.py`)

| buyer | ours | baseline |
|---|---|---|
| cooperative | 73.5 | 69.1 |
| hard_bargainer | 44.7 | 40.8 |
| manipulator | 40.1 | 35.5 |
| **total** | **52.8** | **48.5** |

0 policy / 0 truth violations; 2 deadlocks (baseline 21). Tests: `python -m unittest discover -s tests`.
