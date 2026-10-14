# CineVerse — System Architecture and Design Document
**System Architecture and Design Document · v1.0**

Team 14 (Santhoshraja S, Siddharth P, Keshore G) · 2026-10-14 · Status: Draft for team review

---

> **Purpose.** This is the design document: it fixes the architecture style, module decomposition, interfaces, key design decisions and their rationale. Normative schemas are in the specifications; this document shows how they fit together.

## Contents
1. Design Goals · 2. Architecture Style · 3. Context View · 4. Container and Module View · 5. Interfaces · 6. Runtime View · 7. Data View · 8. Design Decisions (ADRs) · 9. Quality Attribute Scenarios · 10. Design Constraints · 11. Glossary

## 1. Design Goals

| Goal | Design response |
|---|---|
| Compiler stages are real and separable | One module and one data structure per stage; pure functions; per-stage tests |
| Meaning is defined once | Typed IR with documented semantics; canonical plan as reference implementation |
| Optimizations provably safe | Rule preconditions in code; equivalence harness; preservation gate |
| Honest about data | Registry built from the catalogue; `available: false`; unknown fails hard constraints |
| Runs on a student laptop | Python only, CPU, exact search over ~9.7k vectors, no services |
| Demo-able | Trace of every stage rendered by Streamlit |

## 2. Architecture Style

A **modular monolith** organised as a **compiler pipeline** (pipes and filters) feeding an **interpreter** (the executor) over a library of **runtime operators**. Layers (strict, top to bottom): Presentation → Orchestration → Compiler → Contract → Runtime → Data. See Layer Architecture Requirements for allowed dependencies.

## 3. Context View

```
              ┌────────────────────────── CineVerse (local Python app) ──────────────────────────┐
 Viewer ────▶ │ Streamlit UI ─▶ cineverse.recommend() ─▶ compiler ─▶ program ─▶ runtime executor │ ──▶ results + trace
 Examiner ──▶ │                                                                                   │
              └──────────────┬──────────────────────────────┬───────────────────────────────────┘
                             │ one-time download            │ one-time download
                     GroupLens MovieLens            Hugging Face model hub
                     (CSV, pinned checksum)          (all-MiniLM-L6-v2, cached)
```

## 4. Container and Module View

| Package | Modules | Responsibility |
|---|---|---|
| `cineverse.compiler` | `lexicon, lexer, parser, ast, registry, semantic, diagnostics, ir, passes, planner, optimizer, codegen, equivalence, driver` | Text → program; diagnostics; rule log |
| `cineverse.runtime` | `catalog, embeddings, semantic_index, metadata_search, constraints, fusion, scoring, explain, diversity*, executor, trace` | Execute programs; produce results and evidence |
| `cineverse.baseline` | `baseline, popularity` | Hand-wired reference recommender; B0 |
| `cineverse.data` | `prepare, build_index, enrich_tmdb*` | Offline catalogue and index build |
| `cineverse.eval` | `compiler_eval, rec_eval, latency, tune, run_all` | Evaluation and tuning |
| `app` | `streamlit_app` | UI |
| `api*` | `main` | Optional HTTP API |
| `storage*` | `feedback` | Optional SQLite feedback |

`*` = OPTIONAL (P1).

## 5. Interfaces

### 5.1 Stage interfaces
| Function | Module | Signature |
|---|---|---|
| `lex` | `cineverse/compiler/lexer.py` | `lex(text: str, registry: DomainRegistry) -> tuple[list[Token], list[Diagnostic]]` |
| `parse` | `cineverse/compiler/parser.py` | `parse(tokens: list[Token], source: str) -> tuple[RequestNode, list[Diagnostic]]` |
| `analyse` | `cineverse/compiler/semantic.py` | `analyse(ast: RequestNode, registry: DomainRegistry) -> SemanticResult` |
| `lower` | `cineverse/compiler/ir.py` | `lower(sem: SemanticResult, registry: DomainRegistry) -> CompiledQuery` |
| `run_ir_passes` | `cineverse/compiler/passes.py` | `run_ir_passes(ir: CompiledQuery, enabled: set[str]) -> tuple[CompiledQuery, RuleLog]` |
| `build_plan` | `cineverse/compiler/planner.py` | `build_plan(ir: CompiledQuery, cfg: RuntimeConfig) -> LogicalPlan` |
| `optimize` | `cineverse/compiler/optimizer.py` | `optimize(plan: LogicalPlan, ir: CompiledQuery, caps: Capabilities, enabled: set[str]) -> tuple[LogicalPlan, RuleLog]` |
| `generate` | `cineverse/compiler/codegen.py` | `generate(plan: LogicalPlan) -> list[Instruction]` |
| `compile` | `cineverse/compiler/driver.py` | `compile(text: str, *, optimize: bool = True, rules: set[str] = ALL_RULES) -> CompilationResult` |
| `execute` | `cineverse/runtime/executor.py` | `execute(program: list[Instruction], ctx: RuntimeContext) -> ExecutionResult` |
| `recommend` | `cineverse/__init__.py` | `recommend(text: str, *, optimize: bool = True) -> tuple[CompilationResult, ExecutionResult \| None]` |

### 5.2 Compiler ↔ runtime contract
The compiler hands the runtime three artifacts and nothing else:

| Artifact | Type | Defined in |
|---|---|---|
| IR | `CompiledQuery` (Pydantic, v1.0) | IR and Execution Plan Specification §1 |
| Plan | `LogicalPlan` | IR and Execution Plan Specification §4 |
| Program | `list[Instruction]` | IR and Execution Plan Specification §6 |

The executor needs only the program plus a `RuntimeContext` (catalogue, index, config). The IR and plan are passed along for the trace.

### 5.3 RuntimeContext
```python
@dataclass
class RuntimeContext:
    catalog: Catalog                 # runtime/catalog.py
    index: SemanticIndex | None      # None => X201 path
    encoder: Encoder | None
    cfg: RuntimeConfig               # parsed config/runtime.yaml
    caps: Capabilities               # exact_search, semantic_available, mmr_available
```

## 6. Runtime View

### 6.1 Request (happy path)
1. UI calls `cineverse.recommend(text, optimize=toggle)`.
2. Driver: lex → parse → analyse; if ERROR, return `CompilationResult(ok=False)`.
3. Lower → passes → plan → optimize → codegen; record per-stage time.
4. Executor validates and runs instructions with `RuntimeContext`; collects trace.
5. UI renders results, diagnostics and Compiler view from the two result objects.

### 6.2 Start-up
`get_context()` (cached by Streamlit) loads `catalog.parquet`, `registry.yaml` + stats, `runtime.yaml`, the encoder and index; any failure sets the matching capability to false instead of crashing.

### 6.3 Offline build
`prepare` (CSV → parquet + manifest) → `build_index` (embeddings, FAISS, ids, manifest update).

## 7. Data View
| Store | Format | Written by | Read by |
|---|---|---|---|
| `data/raw/ml-latest-small/*.csv` | CSV | user download | `prepare` |
| `data/processed/catalog.parquet` | Parquet | `prepare` | catalog, registry, baseline |
| `artifacts/embeddings.npy`, `ids.npy`, `faiss.index` | NumPy / FAISS | `build_index` | semantic_index |
| `artifacts/manifest.json` | JSON | `prepare`, `build_index` | registry, eval, UI footer |
| `benchmark/requests.jsonl`, `judgments.csv` | JSONL / CSV | team | tests, eval |
| `traces/*.json` | JSON | executor (optional persist) | UI, debugging |
| `results/*.csv`, `*.png` | CSV / PNG | eval | report |
| `storage/feedback.db`* | SQLite | app | eval* |

Schemas: Database and Data Schemas.

## 8. Design Decisions (ADRs)

| ADR | Decision | Alternatives | Rationale |
|---|---|---|---|
| ADR-01 | Natural language in, with a defined sub-language | User-facing DSL; unrestricted NLU | Keeps the product promise and makes the grammar finite and testable |
| ADR-02 | Hand-written recursive descent | PLY, ANTLR, Lark | Small grammar; explicit FIRST sets, lookahead and recovery; precise spans |
| ADR-03 | Registry built from data | Hard-coded fields | Compiler cannot promise fields the data lacks |
| ADR-04 | Pydantic IR with canonical JSON and hash | Plain dicts | Validation, versioning, paraphrase equality |
| ADR-05 | Planner emits one fixed template; optimizer prunes | Smart planner | The template is the reference semantics; all savings are visible rule applications |
| ADR-06 | Exact search (flat FAISS / NumPy) | HNSW | Makes O4 provably safe; 9.7k vectors are fast enough |
| ADR-07 | RRF with constant Z | Weighted score fusion | Robust to scale differences; makes O3 exact |
| ADR-08 | Popularity source only when no positive preference | Always include popularity | Keeps scoring of normal requests unaffected |
| ADR-09 | Remove BM25 | Third retrieval channel | MovieLens text is short; tag matching already covers keywords |
| ADR-10 | No LLM anywhere | LLM parser/explanations | Non-deterministic; breaks equivalence testing; external dependency |
| ADR-11 | Streamlit only (FastAPI optional) | React + API | One-person-week UI that shows every stage |
| ADR-12 | Diagnostics as values | Exceptions | Multiple diagnostics per request; partial results; UI rendering |

## 9. Quality Attribute Scenarios

| Attribute | Stimulus | Response | Measure |
|---|---|---|---|
| Correctness | Optimizer enabled | Same results as unoptimized | 100% equivalence |
| Honesty | "under 2 hours" | S105 shown; no filter applied | Test EX07 |
| Robustness | Index file missing | X201; metadata-only results | `test_executor.py` |
| Performance | 100 requests, warm | Compile p95 < 50 ms; end-to-end p95 < 1.5 s | `latency.py` |
| Modifiability | Replace FAISS with NumPy | No compiler change; same results | `test_semantic_index.py` |
| Testability | Change lexer | Golden ASTs show the diff | golden tests |

## 10. Design Constraints
Python 3.11; CPU; MovieLens latest-small; no network after setup; no secrets in the CORE build; team of three; one semester.

## 11. Glossary
See SRS §9.
