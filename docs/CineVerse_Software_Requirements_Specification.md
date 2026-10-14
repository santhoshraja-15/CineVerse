# CineVerse — Software Requirements Specification (SRS)
**Software Requirements Specification (SRS) · v1.0**

Team 14 (Santhoshraja S, Siddharth P, Keshore G) · 2026-10-14 · Status: Draft for team review

---

> **Purpose.** This SRS states what CineVerse must do and how well, in testable terms. Every requirement has an ID, a priority, a verification method and the module that owns it. Design detail lives in the specifications listed in §1.4; this document does not repeat their schemas.

## Contents
1. Introduction
2. Overall Description
3. Functional Requirements
4. External Interface Requirements
5. Non-Functional Requirements
6. Constraints and Assumptions
7. Requirements Traceability Matrix
8. Acceptance Criteria Summary
9. Glossary

## 1. Introduction

### 1.1 Purpose
CineVerse is a Compiler Design course project. It compiles a natural-language movie request into a validated, typed intermediate representation (IR), an optimized execution plan and three-address instructions, and executes them on a hybrid recommendation runtime that returns ranked, explained movies.

### 1.2 Scope
In scope: English requests within the supported request language; the full compiler pipeline (lexer → parser → semantic analysis → IR → IR passes → planner → optimizer → code generation → executor); semantic and metadata retrieval over MovieLens latest-small; RRF fusion; hard constraints; soft scoring; evidence-based explanations; execution traces; a Streamlit interface; automated tests and evaluation.

Out of scope: a user-facing query language; unrestricted natural-language understanding; generative LLMs; user accounts; production deployment; distributed infrastructure.

### 1.3 Priorities
| Tag | Meaning |
|---|---|
| **P0** | CORE. Required for the course submission and demo |
| **P1** | OPTIONAL. Built only after every P0 acceptance test passes |
| **P2** | Future work; documented, not built |

### 1.4 Related documents
| Document | Role |
|---|---|
| CineVerse_PRD.md | Why and for whom; user stories |
| CineVerse_Technical_Deep_Dive.md | How each component works |
| CineVerse_Compiler_Frontend_Specification.md | Normative: tokens, grammar, AST, registry, semantic rules, diagnostics |
| CineVerse_IR_and_Execution_Plan_Specification.md | Normative: IR, plan, instructions, executor |
| CineVerse_Optimizer_and_Equivalence_Testing_Specification.md | Normative: O1–O4 and equivalence |
| CineVerse_Recommendation_Engine_Specification.md | Normative: runtime operators and scoring |
| CineVerse_Dataset_and_Data_Pipeline_Specification.md | Normative: catalogue |
| CineVerse_Database_and_Data_Schemas.md | Normative: stored data formats |

## 2. Overall Description

### 2.1 Product perspective
A standalone, locally run Python application. One package, `cineverse`, with a `compiler` sub-package and a `runtime` sub-package that meet only at the IR, the logical plan and the instruction list. A Streamlit app is the user interface.

### 2.2 Users
| User | Need |
|---|---|
| Viewer (demo user) | Describe a movie in plain English; get ranked, explained results |
| Examiner / faculty | See every compiler phase working and proven correct |
| Developer (team member) | Build, test and debug one stage at a time |

### 2.3 Operating environment
Windows 10/11, macOS 13+ or Ubuntu 22.04+, Python 3.11, CPU only, 8 GB RAM, about 2 GB free disk. Internet only for the one-time dataset and model download.

## 3. Functional Requirements

### 3.1 Input and lexical analysis
| ID | Requirement | Priority | Verification | Owner |
|---|---|---|---|---|
| FR-01 | Accept a request string of 1–300 characters; otherwise emit S113 and stop | P0 | `test_driver.py` | `compiler/driver.py` |
| FR-02 | Produce typed tokens with `[start, end)` spans into the original text, using longest-match over the phrase lexicon; preserve negation words and numbers | P0 | `test_lexer.py` (≥ 40 cases) | `compiler/lexer.py` |
| FR-02.1 | Resolve multi-word phrases ("science fiction", "not too", "at least") into single tokens | P0 | `test_lexer.py` | `compiler/lexer.py` |
| FR-02.2 | Apply lexicon precedence: genre alias > NEG_SOFT > other closed tables > DESCRIPTOR > FILLER > WORD | P0 | `test_lexer.py` | `compiler/lexicon.py` |

### 3.2 Syntax analysis
| ID | Requirement | Priority | Verification | Owner |
|---|---|---|---|---|
| FR-03 | Parse tokens with a recursive-descent parser implementing the grammar in the Frontend Specification §4 and build the documented AST | P0 | `test_parser.py`, golden ASTs | `compiler/parser.py`, `compiler/ast.py` |
| FR-03.1 | Recover from errors in panic mode (resynchronise at SEP), emitting P001/P002, so every request yields an AST | P0 | `test_parser.py` | `compiler/parser.py` |

### 3.3 Semantic analysis
| ID | Requirement | Priority | Verification | Owner |
|---|---|---|---|---|
| FR-04 | Build a domain registry (symbol table) from `config/registry.yaml` and catalogue statistics; mark fields absent from the catalogue `available: false` | P0 | `test_registry.py` | `compiler/registry.py` |
| FR-05 | Apply semantic rules S1–S13 and emit structured diagnostics (code, severity, message, span, hint) | P0 | `test_semantic.py` | `compiler/semantic.py`, `compiler/diagnostics.py` |
| FR-05.1 | Distinguish hard from soft: "no X" → hard exclusion; "little X", hedged or descriptor exclusions → soft | P0 | `test_semantic.py` | `compiler/semantic.py` |
| FR-05.2 | Never treat an unavailable field or unknown value as satisfying a condition | P0 | `test_semantic.py`, `test_constraints.py` | semantic, runtime |
| FR-05.3 | Stop compilation before planning when any ERROR diagnostic exists | P0 | `test_driver.py` | `compiler/driver.py` |

### 3.4 IR, planning, optimization, code generation
| ID | Requirement | Priority | Verification | Owner |
|---|---|---|---|---|
| FR-06 | Lower the annotated AST to a validated, versioned `CompiledQuery` | P0 | `test_ir.py` | `compiler/ir.py` |
| FR-07 | Run IR passes O2 then O1 and log each application | P0 | `test_passes.py` | `compiler/passes.py` |
| FR-08 | Build the canonical logical plan with the fixed template | P0 | `test_planner.py` | `compiler/planner.py` |
| FR-09 | Apply plan rules O3 then O4 only when their preconditions hold | P0 | `test_optimizer.py` | `compiler/optimizer.py` |
| FR-10 | Prove optimized and unoptimized execution give identical results on every benchmark request | P0 | `test_equivalence.py` | `compiler/equivalence.py` |
| FR-11 | Generate SSA three-address instructions in deterministic topological order | P0 | `test_codegen.py` | `compiler/codegen.py` |

### 3.5 Execution and runtime
| ID | Requirement | Priority | Verification | Owner |
|---|---|---|---|---|
| FR-12 | Validate the program (known opcodes, def-before-use, single assignment, operand types) and execute it with the failure policy (X201, X202) | P0 | `test_executor.py` | `runtime/executor.py` |
| FR-13 | Semantic retrieval with Sentence Transformers + FAISS flat index; NumPy backend with identical results | P0 | `test_semantic_index.py` | `runtime/semantic_index.py` |
| FR-14 | Metadata retrieval over genres and tags; popularity ranking for requests with no positive preference | P0 | `test_metadata_search.py` | `runtime/metadata_search.py` |
| FR-15 | Reciprocal Rank Fusion with constant normalisation Z = 2/(k+1) | P0 | `test_fusion.py` | `runtime/fusion.py` |
| FR-16 | Apply hard constraints only in MASK/FILTER_LIST and soft conditions only in SOFT | P0 | `test_constraints.py`, `test_scoring.py` | `runtime/constraints.py`, `runtime/scoring.py` |
| FR-17 | Generate explanations only from trace evidence | P0 | `test_explain.py` | `runtime/explain.py` |
| FR-18 | Record an execution trace that validates against `trace_schema.json` | P0 | `test_trace.py` | `runtime/trace.py` |
| FR-19 | Provide a hand-wired baseline recommender and prove compiled-unoptimized output equals it | P0 | `test_preservation.py` | `baseline/baseline.py` |
| FR-20 | Regenerate every evaluation table with one command | P0 | `python -m cineverse.eval.run_all` | `eval/` |

### 3.6 Interface
| ID | Requirement | Priority | Verification | Owner |
|---|---|---|---|---|
| FR-21 | Streamlit app: request box, results with reasons, diagnostics with highlighted spans, "Compiler view" tabs, optimizer toggle | P0 | Demo checklist | `app/streamlit_app.py` |
| FR-22 | MMR diversification when "diverse" is requested | P1 | `test_diversity.py` | `runtime/diversity.py` |
| FR-23 | FastAPI endpoints mirroring the app | P1 | `test_api.py` | `api/main.py` |
| FR-24 | TMDB enrichment enabling `runtime` and `language` symbols | P1 | `test_enrich.py` | `data/enrich_tmdb.py` |
| FR-25 | Feedback capture in SQLite | P1 | `test_feedback.py` | `storage/feedback.py` |

## 4. External Interface Requirements

| Interface | Description | Specified in |
|---|---|---|
| User interface | Streamlit single page with results and Compiler view | UI/UX and API Specification §2 |
| Programmatic API | `cineverse.recommend(text, optimize=True)`; optional HTTP API | UI/UX and API Specification §3 |
| Data input | MovieLens latest-small CSV files | Dataset and Data Pipeline Specification |
| Model | `sentence-transformers/all-MiniLM-L6-v2` from the Hugging Face hub, cached locally | Environment Setup |
| Files out | Parquet catalogue, NumPy/FAISS artifacts, JSON traces, CSV results | Database and Data Schemas |

## 5. Non-Functional Requirements

| ID | Category | Requirement | Target | Verification |
|---|---|---|---|---|
| NFR-01 | Portability | Runs on Windows, macOS, Linux with Python 3.11 on CPU | Clean install on each member's machine | Environment checklist |
| NFR-02 | Performance | Compilation (lex → codegen) | p95 < 50 ms | `eval/latency.py` |
| NFR-03 | Performance | End-to-end request after warm-up, 9.7k movies | p95 < 1.5 s on a laptop CPU | `eval/latency.py` |
| NFR-04 | Determinism | Same input, data and config give byte-identical IR and results | 100% | `test_determinism.py` |
| NFR-05 | Correctness | Hard-constraint violations | 0 | `rec_eval.py` |
| NFR-06 | Correctness | Optimizer equivalence and behaviour preservation | 100% | equivalence and preservation tests |
| NFR-07 | Maintainability | Compiler and runtime independently testable; layer rules enforced by test | `test_layers.py` green | CI |
| NFR-08 | Traceability | Every result traceable to request spans through the trace | 100% of results | `test_trace.py` |
| NFR-09 | Usability | A first-time user gets results without reading documentation | Demo dry run | Demo checklist |
| NFR-10 | Offline | No network after the first setup | Offline run passes | Runbook |
| NFR-11 | Privacy | No personal data collected; feedback (P1) stores no identity | Code review | Review |
| NFR-12 | Reproducibility | Data checksums, model name, configs and seeds recorded in manifests | Present for every run | `results/` review |

## 6. Constraints and Assumptions

- MovieLens has no plot, runtime or language fields; requirements depending on them are P1 (FR-24).
- About 1,500 of 9,700 movies have user tags; many movies are described only by title and genres.
- The supported request language is fixed for v1.0 (Frontend Specification §3–§4).
- Team of three, one semester; CPU-only laptops.
- MovieLens "latest" changes over time; the downloaded snapshot is pinned by checksum.

## 7. Requirements Traceability Matrix

| Requirement | Design section | Code | Test | Evaluation evidence |
|---|---|---|---|---|
| FR-01–FR-02 | Frontend Spec §3 | `lexer.py` | `test_lexer.py` | — |
| FR-03 | Frontend Spec §4–§5 | `parser.py`, `ast.py` | `test_parser.py`, golden | AST accuracy |
| FR-04–FR-05 | Frontend Spec §2, §6–§7 | `registry.py`, `semantic.py` | `test_semantic.py` | diagnostic accuracy |
| FR-06–FR-07 | IR Spec §1–§3 | `ir.py`, `passes.py` | `test_ir.py`, `test_passes.py` | IR exact match |
| FR-08–FR-11 | IR Spec §4–§6, Optimizer Spec | `planner.py`, `optimizer.py`, `codegen.py` | planner/optimizer/codegen/equivalence tests | equivalence rate |
| FR-12 | IR Spec §7 | `executor.py` | `test_executor.py` | — |
| FR-13–FR-17 | Recommendation Engine Spec | `runtime/*` | runtime tests | P@10, NDCG@10, violations |
| FR-18 | Logging, Tracing and Observability | `trace.py` | `test_trace.py` | — |
| FR-19 | Optimizer Spec §5 | `baseline.py` | `test_preservation.py` | preservation rate |
| FR-20 | Evaluation Plan | `eval/*` | — | all tables |
| FR-21 | UI/UX Spec | `streamlit_app.py` | demo checklist | — |

## 8. Acceptance Criteria Summary

The system is accepted when: all P0 requirements pass their verification; `pytest -q` is green on a clean clone; equivalence and preservation are 100%; hard-constraint violations are 0; the demo script in the Deployment and Runbook passes; and every reported number is generated by `run_all`.

## 9. Glossary

| Term | Definition |
|---|---|
| AST | Abstract syntax tree produced by the parser |
| IR | Intermediate representation (`CompiledQuery`) |
| Hard constraint | Condition that removes movies; unknown value fails it |
| Soft preference / constraint | Condition that changes score only |
| Registry | Domain registry; the symbol table of the request language |
| SSA | Static single assignment: each register assigned once |
| RRF | Reciprocal Rank Fusion |
| O1–O4 | The four optimization rules |
| S1xx, Pxxx, Lxxx, Xxxx | Diagnostic code families (semantic, parse, lexical, execution) |
