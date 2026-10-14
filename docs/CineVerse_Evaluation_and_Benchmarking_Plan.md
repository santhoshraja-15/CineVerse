# CineVerse — Evaluation and Benchmarking Plan
**Evaluation and Benchmarking Plan · v1.0**

Team 14 (Santhoshraja S, Siddharth P, Keshore G) · 2026-10-14 · Status: Draft for team review

---

> **Purpose.** The experimental protocol: what is measured, on which data, against which baselines, with which safeguards against leakage and bias. **No result is reported unless `python -m cineverse.eval.run_all` produced it.** Targets below are acceptance thresholds set in advance, not results.

## Contents
1. Questions · 2. Benchmark Construction · 3. Relevance Judgments · 4. Systems Compared · 5. Compiler Metrics · 6. Recommendation Metrics · 7. Performance Benchmarks · 8. Protocol and Leakage Controls · 9. Reporting · 10. Threats to Validity

## 1. Questions
| ID | Question | Evidence |
|---|---|---|
| Q1 | Does the front end understand the supported language? | AST accuracy, IR exact match, slot F1 |
| Q2 | Does it reject or flag bad requests correctly? | Diagnostic precision/recall on the invalid set |
| Q3 | Do the optimizations preserve behaviour? | Equivalence 100%, preservation 100% |
| Q4 | Do they save time, and when? | Latency on/off by filter selectivity |
| Q5 | Does compiling intent beat embedding the raw sentence? | NDCG@10 and violations: Compiled vs B2 |
| Q6 | Are hard conditions honoured? | Violation rate = 0 |
| Q7 | Are explanations faithful? | Evidence-support rate = 100% |

## 2. Benchmark Construction
`benchmark/requests.jsonl`, one object per line:

```json
{"id": "R001", "split": "dev", "category": "soft_exclusion",
 "text": "thoughtful sci-fi mystery after 2010, little romance, top 5",
 "gold_ir": { ...canonical CompiledQuery JSON after passes, without source/diagnostics... },
 "gold_diagnostics": [],
 "baseline_spec": { ...BaselineSpec... }}
```

Categories (10 valid × 10 requests): `single_genre, multi_genre, descriptor_only, hard_exclusion, soft_exclusion, year, rating_votes, hedged, limit, combined`; plus 20 `invalid` (contradiction, empty range, unavailable field, unknown field, nonsense). Split: 40 dev / 80 test, stratified by category.

`benchmark/judgments.csv`: `request_id, movie_id, judge, grade(0|1|2)` for 40 valid test requests (pooled Top-10 of all systems, blind).

Rules:
- Written by the team before any tuning; each member writes requests for categories they did not implement.
- Gold IR written from the spec, reviewed by a second member.
- Split frozen with a SHA-256 of the file recorded in `results/run_manifest.json`; `run_all` refuses to run if the test split changed after freeze.

## 3. Relevance Judgments
| Item | Rule |
|---|---|
| Requests | 40 valid test requests (4 per category), plus 16 valid dev requests judged first and used only for tuning |
| Pool | Union of Top-10 from B0, B1, B2, Compiled (Baseline and Compiled+O are equal by construction) |
| Judges | Two members, blind to system; shown title, year, genres, tags, mean rating |
| Grades | 0 not relevant · 1 partly · 2 relevant |
| Agreement | Cohen's κ (weighted) reported |
| Adjudication | Disagreements discussed; `final_grade` recorded |
| Relevant set for Recall | Movies with final_grade ≥ 1 in the pool |

## 4. Systems Compared
| ID | System | Purpose |
|---|---|---|
| B0 | Popularity (Bayesian) over movies passing hard constraints | Non-personal floor |
| B1 | Metadata search + hard constraints | Value of semantics |
| B2 | Raw request embedded as-is, dense search, no constraints | Value of compiling intent (negation, limits) |
| Baseline | Hand-wired recommender from gold specs | Preservation reference |
| Compiled | Unoptimized compiled pipeline | Main system |
| Compiled+O | Optimized compiled pipeline | Must equal Compiled; faster |
| (P1) +MMR | Compiled+O with MMR | Diversity trade-off |

## 5. Compiler Metrics
| Metric | Definition | Target |
|---|---|---|
| Token accuracy | Token sequence (types + values) equals gold | Reported |
| AST accuracy | AST equals golden | ≥ 90% valid test |
| IR exact match | Canonical IR (no spans) equals gold | ≥ 85% valid test |
| Slot P/R/F1 | Over IR elements (each preference/constraint/limit) | Reported |
| Diagnostic precision / recall | Over expected codes on the invalid set | ≥ 90% each |
| Round trip | IR JSON round trip | 100% |
| Plan/program validity | Validators pass | 100% |
| Equivalence | §6 of Optimizer Spec | 100% |
| Preservation | §5 of Optimizer Spec | 100% |
| Compile latency | Lex → codegen | p95 < 50 ms |

## 6. Recommendation Metrics
| Metric | Definition |
|---|---|
| Precision@10 | Relevant (≥ 1) in top 10 / 10 |
| Recall@10 | Relevant in top 10 / relevant in pool |
| NDCG@10 | Graded (0/1/2), log2 discount, ideal from pool |
| MRR | 1 / rank of first grade-2 movie |
| Hard violation rate | Results violating any verifiable hard constraint / results (all valid items) |
| Soft satisfaction | 1 − (results carrying a negative soft match / results) |
| Evidence support | Explanation clauses with evidence / clauses |
| Coverage | Distinct movies recommended / catalogue |

Report mean and 95% bootstrap confidence interval (1,000 resamples over requests, seed 42). Compare systems with a paired permutation test on NDCG@10 (10,000 permutations); report p-values without claiming significance below n = 40 if intervals overlap.

## 7. Performance Benchmarks
| Benchmark | Method |
|---|---|
| Stage latency | 100 warm runs per valid item; p50/p95 per compiler stage |
| Instruction latency | Per opcode, optimizer on/off |
| Selectivity study | Group items by eligible/N: < 0.1, 0.1–0.5, > 0.5; median speed-up per group |
| Cold start | Time to first result after app launch (model + index load) |
| Index build | Time and peak memory of `build_index` |
Record CPU model, RAM, OS, Python and package versions in `run_manifest.json`.

## 8. Protocol and Leakage Controls
1. Tune β, λ, μ, C only on the dev split (`eval/tune.py`, grid β ∈ {0.05, 0.1, 0.2}, λ ∈ {0.1, 0.3, 0.5}, μ ∈ {0.1, 0.2, 0.4}, C ∈ {100, 200, 400}; objective dev NDCG@10 on the 16 judged dev requests). Freeze values in `runtime.yaml` before touching test.
2. Judgments for test requests are collected after freezing.
3. Relevance is judged from metadata, not from held-out user ratings, so there is no rating leakage.
4. Golden files and gold IRs are never regenerated from system output for test items.

## 9. Reporting
`run_all` produces `results/compiler_metrics.csv`, `equivalence.csv`, `recommendation_metrics.csv`, `latency.csv`, plots (`latency_by_stage.png`, `speedup_by_selectivity.png`, `ndcg_by_system.png`) and `run_manifest.json`. Report tables are filled from these files only.

## 10. Threats to Validity
| Threat | Mitigation |
|---|---|
| Small judged set (40) | Confidence intervals; no overclaiming |
| Team-written requests and judgments | Cross-authoring; blind judging; κ |
| Sparse tags | Report coverage; per-category results |
| MovieLens "latest" drift | Checksums in manifest |
| Single hardware | Report hardware; relative comparisons only |
