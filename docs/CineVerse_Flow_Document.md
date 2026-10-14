# CineVerse — Flow Document
**Flow Document · v1.0**

Team 14 (Santhoshraja S, Siddharth P, Keshore G) · 2026-10-14 · Status: Draft for team review

---

> **Purpose.** Every flow in the system, step by step: who calls what, with which data, and what happens on each failure. Use it to trace a bug or to narrate the demo.

## Contents
1. Flow Index · 2. F1 Setup and Offline Build · 3. F2 Request Compilation · 4. F3 Program Execution · 5. F4 Error Flows · 6. F5 Optimizer Toggle and Equivalence · 7. F6 Evaluation · 8. F7 Developer Change Flow · 9. Swimlane Summary

## 1. Flow Index
| Flow | Trigger | Actors | Output |
|---|---|---|---|
| F1 | First setup or data update | Developer | Catalogue, index, manifest |
| F2 | User submits a request | UI, driver, compiler stages, registry | `CompilationResult` |
| F3 | Compilation ok | Executor, runtime operators | `ExecutionResult`, trace |
| F4 | Lexical/syntax/semantic/runtime problem | Compiler, executor, UI | Diagnostics shown; partial or no execution |
| F5 | Examiner flips the optimizer | UI, driver, equivalence harness | Same results, different timings |
| F6 | `run_all` | Evaluation scripts | `results/*.csv` |
| F7 | A member changes code | Developer, pytest | Green suite or a pinpointed failure |

## 2. F1 — Setup and Offline Build
```
Developer
  │ 1. python -m venv .venv; pip install -r requirements.txt
  │ 2. download ml-latest-small → data/raw/ml-latest-small/
  │ 3. python -m cineverse.data.prepare
  │       ├─ checksum raw files → manifest.dataset
  │       ├─ validate columns/types/unique ids   ──✗──▶ abort with the failing check
  │       ├─ parse year, split genres, aggregate ratings, normalise tags
  │       ├─ build embed_text
  │       └─ write catalog.parquet + manifest.coverage
  │ 4. python -m cineverse.data.build_index
  │       ├─ load model (download once)          ──✗──▶ abort: "model unavailable"; app will run metadata-only (X201)
  │       ├─ encode embed_text (batch 64, normalised)
  │       ├─ write embeddings.npy, ids.npy, faiss.index (or skip faiss if backend=numpy)
  │       └─ manifest.model, manifest.index
  ▼ 5. pytest -q   (data + runtime tests)
```

## 3. F2 — Request Compilation
```
UI ─ text ─▶ driver.compile(text, optimize)
  1 lex(text, registry)          → tokens, diags[L001,S113]      S113 ⇒ stop
  2 parse(tokens, text)          → RequestNode, diags[P001,P002]
  3 analyse(ast, registry)       → SemanticResult, diags[S101–S114]
        any ERROR?  ── yes ──▶ return ok=False (F4)
  4 lower(sem, registry)         → CompiledQuery (ir_lowered)
  5 run_ir_passes(ir, {O2,O1})   → ir, rule_log
  6 build_plan(ir, cfg)          → plan_unoptimized
  7 optimize(plan, ir, caps, {O3,O4}) if optimize else (plan, [])
  8 generate(plan)               → program
  9 return CompilationResult(ok=True, timings per step)
```
Data handed between steps is immutable; each step's output is stored in the result for the trace.

## 4. F3 — Program Execution
```
executor.execute(program, ctx)
  0 validate: opcodes, def-before-use, SSA, operand types   ──✗──▶ ERROR (bug), no execution
  for each instruction (in order):
     t0 = now
     SCAN        → all ids
     MASK        → ids satisfying hard preds (unknown ⇒ fail)       empty ⇒ X202, short-circuit to empty results
     SEM_SEARCH  → RankedList (exact, scoped)                       index/model missing ⇒ X201, empty list
     META_SEARCH → RankedList (genres + tag terms)
     POP_RANK    → RankedList (Bayesian rating)
     FILTER_LIST → filtered, renumbered, truncated (unoptimized plans only)
     RRF         → fused, /Z
     SOFT        → + β matches − λ negatives − μ soft violations
     MMR*        → diversified
     TOPK        → first n
     EXPLAIN     → Recommendation[] with reasons from evidence
     record {opcode, ms, out_size, sample}
  RET → ExecutionResult(results, trace, diagnostics)
UI renders cards + Compiler view
```

## 5. F4 — Error Flows
| Stage | Example | Code | Behaviour |
|---|---|---|---|
| Input | "" or 400 characters | S113 | Stop at lexing; message only |
| Lexical | "sci-fi ★★★" | L001 | Character skipped; continue |
| Syntax | "drama, stars" | P001 | Skip to the next synchronising token; continue |
| Syntax | "comedies 42" | P002 | Number ignored; continue |
| Semantic | "rated above 9" | S104 | Stop before planning |
| Semantic | "only horror and no horror" | S107 | Stop; both spans highlighted |
| Semantic | "after 2015 before 2000" | S108 | Stop |
| Semantic | "comedy under 2 hours" | S112, S105 | Continue without runtime filter; warning shown |
| Semantic | "no gore" | S106 | Continue; soft penalty |
| Semantic | "something please" | S111 | Stop |
| Runtime | index missing | X201 | Continue metadata-only; warning shown |
| Runtime | "only documentaries rated at least 5 after 2018" (nothing qualifies) | X202 | Empty results with explanation |
| Runtime | unexpected exception | ERROR | Stop; partial trace saved |

## 6. F5 — Optimizer Toggle and Equivalence
```
UI toggle off → compile(text, optimize=False) → execute → results_U, timings_U
UI toggle on  → compile(text, optimize=True)  → execute → results_O, timings_O
UI shows: results identical? ✓   rules applied: O2, O4   time saved in SEM_SEARCH/META_SEARCH
Test harness (equivalence.py): for every benchmark item and for each rule alone and all rules:
   assert ids_U == ids_O and round(scores,6) equal and hard outcomes equal and diagnostics equal
```

## 7. F6 — Evaluation (`python -m cineverse.eval.run_all`)
1. Load frozen config and benchmark; assert test split untouched since freeze (hash).
2. Compiler metrics on all items → `results/compiler_metrics.csv`.
3. Equivalence and preservation → `results/equivalence.csv`.
4. Systems B0, B1, B2, Baseline, Compiled, Compiled+O on judged test requests → `results/recommendation_metrics.csv`.
5. Latency: 100 warm runs per stage and per instruction, optimizer on/off → `results/latency.csv` + plots.
6. Write `results/run_manifest.json` (git commit, config hashes, dataset checksum, model).

## 8. F7 — Developer Change Flow
1. Pick the next unticked task in the Roadmap; read its spec section.
2. Write or update tests first (golden files for parser changes).
3. Implement within the files the task names.
4. `pytest -q`; if a golden file changes, review the diff and update it deliberately.
5. Update CHANGELOG and spec if an interface changed; commit `step N: …`.

## 9. Swimlane Summary
| Lane | F1 | F2 | F3 | F4 | F5 | F6 |
|---|---|---|---|---|---|---|
| UI | — | send text | render | show diagnostics | toggle | — |
| Compiler | — | all stages | — | emit L/P/S codes | run twice | compiler metrics |
| Executor | — | — | run program | emit X codes | run twice | latency |
| Runtime ops | — | — | operators | — | — | systems |
| Data | build | registry stats | catalogue, index | — | — | — |
