# AgentX PS2 — Selling to Machines

Seller agent for Techfest IIT Bombay 2026–27, Problem Statement 2.

- `kit/` — official starter kit, unmodified (re-download before the final run).
- `seller/` — our seller (deterministic, std-lib only; entry `seller/agent.py:Seller`). *(in progress)*
- `bench/` — extra rule-based and LLM buyers for testing. *(in progress)*
- `HANDOFF_01_agentx.md` — plan and decisions.

```
python kit/evaluate.py                                   # baseline (48.5)
python kit/evaluate.py --seller seller/agent.py --log logs/transcripts.jsonl
```

LLM test buyers need `GEMINI_API_KEY` (environment variable, or `.env` — see `.env.example`).
