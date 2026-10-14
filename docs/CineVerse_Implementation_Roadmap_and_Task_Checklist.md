# CineVerse — Implementation Roadmap and Task Checklist
**Implementation Roadmap and Task Checklist · v1.0**

Team 14 (Santhoshraja S, Siddharth P, Keshore G) · 2026-10-14 · Status: Draft for team review

---

> **Rule.** Steps run in order. A step is closed only when every exit criterion is ticked on a clean checkout. **No optimizer code is written before step 9 (behaviour preservation) is closed.** Task IDs (T01–T34) are the same as in the Claude Code Master Instructions, which contain the exact prompt for each task.

## Contents
1. Milestones · 2. Step-by-Step Checklist · 3. Optional Tasks · 4. Human Tasks · 5. Weekly Cadence

## 1. Milestones
| Milestone | Steps | Tasks | Exit evidence |
|---|---|---|---|
| M1 Foundation | 1–4 | T01–T10 | Baseline returns results for 10 hand specs |
| M2 Front end | 5–7 | T11–T16 | Golden ASTs; S-rule tests; IR tests |
| M3 Back end | 8–9 | T17–T21 | Preservation 100% |
| M4 Optimizer | 10 | T22–T25 | Equivalence 100% |
| M5 Product | 11–12 | T26–T28 | Example JSON test green; demo checklist |
| M6 Evidence | 13–14 | T29–T30 | `run_all` tables; verification checklist |

## 2. Step-by-Step Checklist

### Step 1 — Freeze scope and interfaces
- [x] **T01** All members read SRS, Frontend, IR, Optimizer and Engine specs; open questions resolved in Project Control decision log.
- [x] **T02** First 20 benchmark items (2 per valid category) with gold IR, gold diagnostics and baseline specs.
- Exit: specs v1.0 signed off; `benchmark/requests.jsonl` has 20 reviewed items.

### Step 2 — Repository and environment
- [x] **T03** Repo scaffold, `requirements.txt`, `pyproject.toml` (ruff, pytest config), `test_smoke.py`, `test_layers.py`, `scripts/check.sh|ps1`.
- Exit: clean install on all three laptops; `pytest -q` green; `requirements.lock` committed.

### Step 3 — Dataset
- [x] **T04** `data/prepare.py`, `runtime/catalog.py`, D1–D7 checks, manifest.
- Exit: `catalog.parquet` + manifest; data tests green.

### Step 4 — Runtime operators and baseline
- [x] **T05** `runtime/embeddings.py`, `data/build_index.py` (I1–I6).
- [x] **T06** `runtime/semantic_index.py` (FAISS flat + NumPy, scoped search).
- [x] **T07** `runtime/metadata_search.py` (search + popularity).
- [x] **T08** `runtime/constraints.py`, `runtime/fusion.py`, `runtime/scoring.py`.
- [x] **T09** `runtime/explain.py` + `Recommendation`.
- [x] **T10** `baseline/baseline.py`, `baseline/popularity.py`.
- Exit: runtime tests green; baseline answers 10 hand specs; FAISS = NumPy.

### Step 5 — Lexer, parser, AST, diagnostics
- [x] **T11** `compiler/diagnostics.py`, `compiler/lexicon.py`, `compiler/lexer.py`.
- [x] **T12** `compiler/ast.py`, `compiler/parser.py`.
- [x] **T13** Golden-file tooling `tests/golden/regenerate.py`; golden tokens and ASTs for all benchmark items.
- Exit: lexer (≥ 40) and parser (≥ 30) tests; golden files reviewed.

### Step 6 — Registry and semantic analysis
- [x] **T14** `compiler/registry.py`.
- [x] **T15** `compiler/semantic.py` (S1–S13).
- Exit: every S-rule has ≥ 3 tests; invalid benchmark items produce gold codes.

### Step 7 — IR
- [x] **T16** `compiler/ir.py` (models, lowering, V1–V5, to_json, hash, from_json).
- Exit: IR tests; dev IR accuracy measured (lists compared as sets until O2 exists).

### Step 8 — Planner, codegen, executor
- [x] **T17** `compiler/planner.py` (template, validate).
- [x] **T18** `compiler/codegen.py` (order, SSA, printed form).
- [x] **T19** `runtime/executor.py`, `runtime/trace.py`, `runtime/trace_schema.json`.
- [x] **T20** `compiler/driver.py`, `cineverse/__init__.py::recommend`.
- Exit: plan and program validity 100%; unoptimized programs match `program_unoptimized` in the example JSON.

### Step 9 — Behaviour preservation (gate)
- [x] **T21** `tests/test_preservation.py`; baseline specs for every benchmark item.
- Exit: 100% equal. **Gate for step 10.**

### Step 10 — Optimizer (one rule at a time)
- [x] **T22** O2 in `compiler/passes.py`.
- [x] **T23** O1 in `compiler/passes.py`.
- [x] **T24** O3 in `compiler/optimizer.py`.
- [x] **T25** O4 in `compiler/optimizer.py`; `compiler/equivalence.py`; `test_equivalence.py`; property tests.
- Exit: each rule's positive/negative tests; equivalence 100% for each rule alone and all rules; optimized programs match the example JSON.

### Step 11 — Tuning and examples
- [ ] **T26** `eval/tune.py` on dev split; freeze `runtime.yaml`.
- [x] **T27** `tests/test_examples.py` over all 25 entries in the example JSON.
- Exit: zero violations; explanation tests; example test green.

### Step 12 — Interface
- [ ] **T28** `app/streamlit_app.py` per UI/UX Specification.
- Exit: UI acceptance checklist passes.

### Step 13 — Evaluation
- [ ] **H1** Remaining 100 benchmark items written and reviewed; split frozen.
- [ ] **H2** Dev judgments (16) then, after tuning, test judgments (40); κ.
- [ ] **T29** `eval/compiler_eval.py`, `eval/rec_eval.py`, `eval/latency.py`, `eval/run_all.py`.
- Exit: all results files produced by one command.

### Step 14 — Documentation and release
- [ ] **T30** README, CHANGELOG, report tables from `results/`, clean-install check, demo rehearsal, viva practice.
- Exit: Deployment and Runbook §6 and Testing Plan §9 checklists complete.

## 3. Optional Tasks (only after M6)
| Task | Content | Spec |
|---|---|---|
| T31 | MMR (`runtime/diversity.py`, DIVERSIFY/MMR op, `mmr_available`) | Engine Spec §2 (11.7) |
| T32 | TMDB enrichment (`data/enrich_tmdb.py`) | Dataset Spec §7 |
| T33 | FastAPI (`api/main.py`) | UI/UX and API Spec §4 |
| T34 | SQLite feedback (`storage/feedback.py`) | Database and Data Schemas §8 |

## 4. Human Tasks
| ID | Task | Owner | When |
|---|---|---|---|
| H1 | Write and review 120 benchmark requests | All (cross-authoring) | Steps 1 and 13 |
| H2 | Relevance judgments, blind | Two members | Step 13 |
| H3 | Review every golden-file diff | Stage owner | Continuous |
| H4 | Report writing from `results/` | All | Step 14 |

## 5. Weekly Cadence
Monday: pick tasks, update Project Control status. Daily: one task → tests → commit. Friday: run full `pytest -q`, update milestone status, note risks.
