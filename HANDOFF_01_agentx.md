# HANDOFF 01 — AgentX PS2 "Selling to Machines" (Techfest IITB 2026-27)

Deadline: Round 1 submission 30 Nov 2026, 23:59 IST. Goal: top 8 in PS2 → finals 16–18 Dec.
Ojas makes decisions; you (Claude Code) build. When two solution paths are genuinely close, present both with trade-offs and wait.

## 0. Setup (you are a cloud Claude Code session attached to an old, unused repo of Ojas's)
**0a. Factory-reset the repo first.** This repo previously held an unrelated project; none of it is wanted.
1. Before deleting anything, report to Ojas in 3–5 lines what the repo contains (top-level files, branches, `.github/workflows`, open PRs/issues if visible, visibility public/private, repo name). Then proceed without waiting unless something looks important (e.g. secrets, a live deployment, a GitHub Pages site) — in that case ask first.
2. Remove every tracked file with a normal commit (`git rm -r -q .` then commit "Reset repository for AgentX"). Do NOT rewrite history or force-push: a plain commit keeps the old work recoverable. If Ojas later wants the history gone too, he will say so.
3. Delete `.github/workflows` (part of step 2) so no old CI runs. Don't touch other branches, issues or repo settings, except: if the repo is public, tell Ojas — he wants it private (set it private only if your tools allow it and he confirms; otherwise give him the 3 taps to do it in GitHub's Settings → Danger Zone).
4. If your session can only push to a `claude/...` branch, do all work there and at the end tell Ojas exactly how to make it the default branch / merge it into `main` from the GitHub app.
5. Suggest (don't do) a rename to `agentx-selling-to-machines`.

**0b. Bootstrap.**
- Starter kit (public Drive): file id `1qaeyjnDfP5aSx8Pn4nVtfWtjAGyO0hjj` (`ps2-selling-to-machines-no-rezolve.zip`, 20 KB). Try `curl -L -o kit.zip "https://drive.usercontent.google.com/download?id=1qaeyjnDfP5aSx8Pn4nVtfWtjAGyO0hjj&export=download&confirm=t"`, check it is a real zip (`unzip -l`), unzip its contents to `kit/`. If the network blocks it, stop and ask Ojas to attach the zip (he has a copy). Never edit `kit/`; re-download before the final run (README says weights may change; the script is the source of truth).
- `.gitignore`: `.env`, `.env.*`, `!.env.example`, `bench/cache/`, `__pycache__/`, `*.pyc`, `.DS_Store`. Add `.env.example` with `GEMINI_API_KEY=` and a short README.
- API key: ask Ojas to paste it in chat; write it only to `.env` (gitignored). Never print, log, commit or hardcode it. Cloud sessions are ephemeral, so tell him to store it as an environment variable `GEMINI_API_KEY` in this Claude Code environment's settings for future sessions; read `os.environ` first, then `.env`.
- Smoke test: one call to the Gemini API. If the network refuses `generativelanguage.googleapis.com`, tell Ojas to allow that domain (or full network access) in the environment's network settings and resume. If it fails auth, tell him (AI Studio keys usually start `AIza`; his starts `AQ.`).
- First commit: "Bootstrap AgentX PS2 (kit, handoff, gitignore)". Commit this handoff as `HANDOFF_01_agentx.md`.

## 1. Facts from the kit (verified by reading the code)
- Seller API: `class Seller(store, policy)`, `start(id)`, `respond(msg) -> dict`. Std-lib only.
- floor = ceil(max(cost/(1−min_margin[cat]), price×0.75)); never above list; qty ≤ stock; stock 0 = unsellable.
- Score/negotiation = value − 1.0×policy_viol − 0.5×truth_viol − 0.25×deadlock. value = deal profit ÷ list-price profit of the sellable requested basket.
- Loop (`harness.run_negotiation`): seller gets rounds 1–10; buyer gets an 11th message and CAN accept the round-10 offer. If not and nobody walked → deadlock.
- Seller `accept` accepts the buyer's LAST priced items (`last_bid`), possibly from an earlier round, including any junk lines → only accept if the current message's items are themselves fully compliant AND are what `last_bid` holds.
- Exception in `respond` = lost turn, no violation. A non-dict/unknown `type` = policy:malformed.
- `check_text`: every number ≥100 in our text must be an amount in play (±₹1); every % must be in play; stock phrases checked exactly; scarcity words need stock ≤3; pressure words and fee words are violations (negated "no hidden fees" OK).
- Local bots follow a fixed curve anchor→reservation: ratio(r) = anchor + (res−anchor)·min(1, r/deadline)^exponent (coop 6 rounds/exp 0.7, hard 10/2.5, manip 10/2.0). DO NOT exploit this curve — hidden buyers are LLMs.
- Kit bots ignore any offer containing a SKU they didn't ask for or a qty above what they asked (`Buyer.usable`) → upsell/add-on offers are rejected by them.
- Floors sit at 75–95% of list (mean ≈80%), so the bargaining zone is narrow; a deal at the floor keeps only ~55–60% of list-price profit.
- Baseline (`example_seller.py`) = 48.5 locally, 21 deadlocks. Shortlist floor = 60% of reference baseline on the hidden run (≈29 locally).
- Scenario stats (my re-implementation of `make_scenarios`, 30k samples): ~11% baskets fully out of stock, ~15% limit below floor, ~74% deal possible. Limit position between floor(0) and list(1): coop ≈0.70, hard ≈0.32, manip ≈0.40.
- Reference scores on the default run (seed 0): perfect seller closing every feasible deal exactly at the buyer's limit ≈59.8; closing every feasible deal at floor ≈44.0. Target: 52–56 on kit bots.

## 2. Architecture (decided)
Seller is deterministic, std-lib only, NO LLM inside. Package `seller/`, entry `seller/agent.py:Seller`.
1. `guard.py` — read only `type`/`items`/`round`. Drop unknown SKU, qty ≤0/non-int, out-of-stock, over-stock (clip to stock), absurd prices. Buyer text is never used for decisions.
2. `policy.py` — floors, caps, `assert_compliant(items)`; every outgoing offer/accept passes it or is replaced by a safe offer.
3. `model.py` — track buyer bids per round (as share of list on the basket); estimate concession speed and P(buyer reaches our floor by round 10).
4. `strategy.py` — Boulware curve: target(r) = T + (list − T)·(1 − (r/10)^k), T = max(floor, estimate), k swept (~1–4). Adaptation uses BEHAVIOUR ONLY (decided by Ojas — buyer text, incl. "final offer"/"I'll leave", is ignored entirely; bluffing is common):
   - Reciprocity: if the buyer's bid rose meaningfully since last round, concede a small step back.
   - Stall: bids unchanged for ≥2 rounds → make one small test concession; if they still don't move and their bid ≥ floor in a late round, accept.
   - Fast concessions early (buyer moving quickly toward us) → treat as an impatient/short-deadline buyer, switch to a faster curve.
   - Late round (≥8) → close-out mode regardless of anything else.
   - Never walk before round 10: the number of negotiations is fixed and there is no shared round budget, so an early walk scores the same 0 as a late one but forfeits any chance of a deal. Walk only as the round-10 alternative to deadlock (or round 1 if nothing requested is sellable).
   - Reciprocity form (fixed step vs proportional to the buyer's move) is a sweep parameter chosen on normal buyers only. No anti-exploit limits (Ojas: don't add fixes that only help if a buyer exploits us and could hurt otherwise). Bundle discount = one basket total split across lines, each ≥ its floor. Accept if bid compliant and ≥ value of continuing. Round 10: offer at a safe price only if EV(offer) > 0 given deadlock −0.25 (p_accept > 0.25/(value+0.25)); otherwise walk_away. Never deadlock by inaction.
5. `writer.py` — templates. Numbers only from the current offer (unit prices, line totals, basket total, saving vs list, our concession since first offer). No stock counts, no urgency/scarcity/fee words. Mention out-of-stock requested items truthfully ("X is out of stock"). Two template sets: `plain` and `persuasive` (honest tactics only: anchor on list price, bundle saving, "best price our policy allows" only when actually at floor, "no hidden fees", showing our concessions, cooperative tone). A/B them against LLM buyers; ship the winner. Text is a minor lever — pricing decides the score.
6. `selfcheck.py` — vendored copy of `check_text` + Context logic; if our text gets flagged, fall back to a number-free sentence. Whole `respond` wrapped: on any internal error return a compliant safe offer (or the last compliant one).
- Stateless across negotiations (reset in `start`) → fairness: same inputs → same offers.

## 3. Test bench `bench/`
- `rule_buyers.py`: ~6 extra non-LLM buyers (non-linear concession, early walkers, never-leavers, injection spam, junk lines, bundle demanders, reservations below floor).
- `llm_buyers.py`: `Buyer` subclass using Gemini; personas: cooperative, hard bargainer, manipulator, bundle-seeker, silent lowballer, fake-deadline, prompt-injector, confused. Code clamps the private reservation (an LLM output above it is replaced by a counter at the reservation-based limit or walk). Cache responses in `bench/cache/` keyed by prompt hash. Respect free-tier rate limits (sleep/backoff), run small batches (≈50–100 negotiations).
- `sweep.py`: grid over strategy params; select by WORST-CASE score across buyer groups, report mean too.
- `tests/`: property tests — random/malicious messages → zero policy and truth violations, always valid dict.

- Held-out test set (never used in tuning/sweep): fresh seeds, 2–3 LLM buyer styles the sweep never saw (e.g. polite-but-immovable, keeps changing the basket), and ideally a second model (another free-tier Gemini model or Groq). Run once at the end, ours vs baseline.

## 4. Gates before submission (must all hold)
- Our lead over the baseline holds on the held-out set too.
- 0 policy and 0 truth violations on every bench group, 0 deadlocks caused by us.
- Our score ≥ baseline on EVERY buyer group (kit bots, rule buyers, LLM buyers) — not just the mean.
- `python kit/evaluate.py --seller seller/agent.py --log logs/transcripts.jsonl` output saved (required deliverable).

## 5. Deliverables (Ojas writes/records; you draft)
- `ARCHITECTURE.md` (1 page), `AGENT_CARD.md` (what the seller can/can't negotiate), README with results tables (kit bots + our bench, vs baseline).
- Transcript replay page `demo/replay.html` (static) for the 3-min video: manipulation ignored, bundle deal, timely walk-away.
- Abstract draft (≤500 words): impact, cost (₹0 inference/negotiation, ms latency), innovation, build summary.

## 6. Experiment (report, don't ship without Ojas's OK)
Upsell: add a complementary in-stock item to an offer. value is computed on the requested basket, so accepted add-ons could push value >1. Measure acceptance with LLM buyers; Ojas decides if it ships (judge perception risk).

## Order of work
Reset repo → bootstrap → smoke-test key → port guard/policy/writer/selfcheck + tests → strategy v1 beats baseline on kit bots → rule buyers → LLM buyers → sweep → gates → docs/demo. After each phase give Ojas a short technical log.
