# S6E10 — Phase 0 method note (24 Oct 2026, 7 days left)

## Confirmed facts
- **Metric** ROC AUC. **Submission** `id,satisfaction` with header, one probability per test id. **Deadline** 31 Oct 2026 23:59 UTC. *(Overview page)*
- Train 699,635 / test 299,844 rows. Original data has 129,880 rows and **3,821 unique Flight Distance values** (median 12 rows each; 80% of rows sit on values seen ≥20×). The original-data figures were checked locally; the comp-data ones come from the notebook EDA.
- **Your account has not joined the competition yet**, so the comp-data download returns 403 and the checks in `scripts/verify.py` have not run. Click *Join Competition* at kaggle.com/competitions/playground-series-s6e10.
- **The target is out of date.** Public LB today: r10 0.96215 · r100 0.96213 · r300 0.96190 · r577 **0.96180** · r1000 0.96093. 0.96042 now ranks about 1,224th.
- **Leaders stack public OOFs.** About 200 public OOF/test pairs exist, almost all on `StratifiedKFold(5, shuffle=True, random_state=42)`, the same folds as ours. An L2 logistic-regression stack over them (C=0.003) scores nested CV 0.96217 and LB 0.96181 *(yeashusemwal, cdeotte)*.
- **The top 0.96207–0.96213 files are blends fit to the public LB.** They have no OOF behind them, and their authors say so *(rabari9999)*. goodpjw2008 measured the public-LB slope of the #1 file at 0 ± 0.8e-5 against a CV slope of +9.4e-5. These files will likely drop on the private LB, while an honest CV stack should hold.
- **CV−LB gap** ≈ 0.0004–0.0005 everywhere. Public-LB noise between two strong files ≈ 1e-4, so pick by CV.

## Your claimed findings: status (sourced = from write-ups, not re-run)
| Claim | Status |
|---|---|
| FD ≈ route ID; route count + profile = biggest gain | Original data: **verified** (3.8k unique). Gain sourced: count +0.00060, profile +0.00065 *(bernard)*; profile +0.00010 on top of TE *(dvorkin)* |
| Ratings as categoricals small gain | Consistent: num→cat +0.00004 *(dvorkin)* |
| Row summaries / residuals hurt | **Mixed.** −0.00017 / −0.00015 / −0.00012 *(bernard)*, but per-route residuals inside the profile gave +0.00010 *(dvorkin)* |
| Appending original rows hurts | **Hearsay only** ("forum competitors", Nishant). No measured number |
| Original-only teacher helps | Confirmed, and larger than you claimed: +0.00018 *(bernard)*, ≈+0.0005 *(Nishant)*, **+0.00055** *(dvorkin)* |
| Fold-safe TE on FD/Age/FD×Class/FD×ToT | +0.00016 *(bernard)*; 3 smoothings (auto/10/100) over 44 keys +0.00038 *(dvorkin)* |
| GBDTs ≈0.9603 each; blend +0.0004 | Newer numbers: v2 GBDTs 0.96069–0.96078, blend 0.96093 *(Nishant)*. Best public single LGBM 0.96111 *(dvorkin)* |
| Reference CV 0.9609 / LB 0.9604 = rank 577 | This was Nishant's v2. It is **now about rank 1,224** |

## Beyond that (what the top notebooks do)
Digit features of Age/FD/delays (+0.00069 at the baseline), frequency encoding, pair TE, exact-key lookups into the original data, and aux-task features (predicting other columns; goodpjw parts 4–6, 0.96127 → 0.96152 LB). Tabular foundation models: TabPFN-3.5 with `n_estimators=4` is the best honest single model (OOF 0.96149), alongside Kumo, TabICL-2, Mitra and LimiX. RealMLP (pytabkit) treats every column as categorical and target-encodes combinations. **Pseudo-labels hurt:** +0.00003 CV but −0.00004 LB, because the teacher's test predictions carry the labels.

## Ranked experiments (expected gain over our own ~0.9611 GBDT stack · compute)
1. **E1 Public-OOF LR stack.** Pin dataset versions with md5, nested meta-CV (rs=7), C sweep. Drop members flagged as leaky (early stopping on the held-out fold, pseudo-labels) and any member with single OOF > 0.9620. **+0.0005–0.0010 → nested CV ≈0.9621, LB ≈0.9618.** About 10 min of CPU on Colab, no GPU.
2. **E2 Our LGBM** with route count/profile, digits, frequency, multi-TE and the original teacher, on our folds. On its own ≈0.9611; in the stack it adds diversity, +0.00000–0.00005. About 20 GPU-min.
3. **E3 XGB + CatBoost (GPU) on the E2 features, plus RealMLP.** Stack gain ≈ +0.00002. About 40 GPU-min.
4. **E4 Aux-task features** in E2. +0.00005 on single models, ≈ +0.00001 in the stack. About 20 GPU-min.
5. **Skip:** TabPFN reruns (saturated in the stack, ±0), pseudo-labels, appending original rows, LB probing.

**Final picks:** (a) best nested-CV stack; (b) plain LR stack plus our members at fixed weight, as the most robust option. Neither pick is fit to the LB.

## Risks
- Public OOF files can change upstream: pin md5s and copy them to Drive.
- Some members leak (per their own authors' disclosures). Vet each member. Nested CV is mandatory, because a flat-CV stack over-reports.
- The r1 score of 0.96407 is a lone outlier; ignore it.
- Only 7 days remain, so Phases 2–3 must shrink to E2–E4. Colab disconnects are handled by per-fold checkpoints.
- TabPFN members carry a non-commercial licence; their authors say it allows Kaggle use.
