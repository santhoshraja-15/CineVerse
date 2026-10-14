# CineVerse — Product Requirements Document
**Product Requirements Document · v1.0**

Team 14 (Santhoshraja S, Siddharth P, Keshore G) · 2026-10-14 · Status: Draft for team review

---

## Document Control

### Revision history
| Version | Date | Author | Change |
|---|---|---|---|
| 0.1 | 2026-10-13 | Team 14 | Intent-aware recommender concept (submitted report) |
| 0.9 | 2026-10-13 | Team 14 | Compiler-centric redesign; CORE/OPTIONAL/REMOVE scope |
| 1.0 | 2026-10-14 | Team 14 | Documentation set v1.0 |

### Reviewers and approval
| Name | Role | Status |
|---|---|---|
| Santhoshraja S | Team member | Pending |
| Siddharth P | Team member | Pending |
| Keshore G | Team member | Pending |
| Course faculty | Reviewer | Pending |

### How to read this document
This PRD says what CineVerse is and why each feature exists. Requirement IDs (FR-xx, NFR-xx) are the same as in the SRS. How each component works is in the Technical Deep-Dive; build steps are in the Claude Code Master Instructions.

## Contents
1. Executive Summary · 2. Background and Problem · 3. Comparable Systems · 4. Vision and Strategy · 5. Goals and Success Criteria · 6. Personas · 7. User Stories · 8. Scope · 9. Functional Requirements · 10. Non-Functional Requirements · 11. Architecture and Stack · 12. Data and Integrations · 13. UX Requirements · 14. Assumptions and Constraints · 15. Risks · 16. KPIs · 17. Release Plan · 18. Team · 19. Future Roadmap · 20. Glossary

## 1. Executive Summary

### 1.1 What CineVerse is
A movie recommender you talk to in plain English, built as a compiler. "Thoughtful sci-fi mystery after 2010, little romance, top 5" is lexed, parsed, type-checked, lowered to a typed IR, optimized and compiled into a small program that a hybrid recommendation engine executes. The user gets five movies with reasons; the examiner can open every stage in between.

### 1.2 The core insight
> **Core insight.** A movie request is a tiny program. Its words have types (genre, mood, year, rating), its clauses have structure, and it can be wrong (contradictory, out of range, asking for data that does not exist). Treating it as a program, with a grammar, a symbol table, an IR and semantics-preserving optimization, gives a recommender properties that embedding search alone cannot: "no horror" really removes horror, "little romance" only lowers it, "under 2 hours" is refused honestly when the data has no runtime, and every result can be traced back to the words that caused it.

### 1.3 Why it wins (for this course)
- Every classical compiler phase is present as a real, tested module, on a problem a non-specialist instantly understands.
- Correctness is provable, not asserted: optimized ≡ unoptimized and compiled ≡ baseline are tests.
- The demo is visual: type a sentence, then walk through tokens, AST, IR, plans and instructions.

## 2. Background and Problem Statement

### 2.1 Why now
Sentence embeddings (Sentence-BERT) and fast vector search (FAISS) made meaning-based search cheap enough for a laptop. They did not make it precise: an embedding of "no horror" sits close to horror.

### 2.2 The evidence
- The team's existing system needed a seed movie, used bag-of-words features and an N × N similarity matrix, and ignored negation.
- Pure vector search cannot enforce numeric limits ("after 2010") or exclusions, and cannot say why a movie was chosen.
- MovieLens, the standard research catalogue, lacks runtime and plots, so any system that silently "applies" such conditions is misleading its user.

### 2.3 Problem statement
Users cannot state precise, mixed intent (preferences, exclusions, numeric limits) to a recommender and get results that honour it and explain themselves. CineVerse compiles the request into a checked, optimizable plan so that every condition is either enforced, applied softly, or reported as unsupported, and every result is explained from evidence.

## 3. Comparable Systems

| System type | What it does | Gap CineVerse closes |
|---|---|---|
| Genre/filter UIs (streaming apps) | Checkbox filters | No free text; no soft preferences |
| Collaborative filtering | "Users like you watched" | Needs history; cannot take a request |
| Pure semantic search | Embeds the sentence | Negation attracts the excluded genre; no hard limits; no reasons |
| Existing team system | Similar movies to a chosen one | No sentence input; N² memory; no negation |
| LLM chat recommenders | Free-form answers | Non-deterministic, can invent movies, untestable |

## 4. Vision and Product Strategy

### 4.1 Vision
Describe the film you want in your own words and get an honest, explained answer, with a compiler that shows its work.

### 4.2 Strategy
Wedge: a small, precise request language over MovieLens with a complete, provably correct compiler. Growth (future): richer metadata (TMDB), multi-turn refinement compiled as IR patches, title references ("like Inception").

### 4.3 Guiding principles
1. Compiler first; the recommender is the target runtime.
2. Never claim what the data cannot verify.
3. Optimizations never change results.
4. Deterministic and reproducible.
5. Small and finished beats large and unfinished.

## 5. Goals and Success Criteria

### 5.1 Product goals
| Goal | Measure |
|---|---|
| Understand supported requests | IR exact match ≥ 85% on valid test requests |
| Honour hard conditions | 0 hard-constraint violations |
| Catch bad requests | Diagnostic accuracy ≥ 90% on invalid requests |
| Optimize safely | Equivalence 100%; preservation 100% |
| Be fast enough to demo | End-to-end p95 < 1.5 s; compile p95 < 50 ms |
| Recommend well | NDCG@10 of Compiled ≥ B2 (raw semantic) on the judged set (hypothesis, measured) |

### 5.2 Definition of done (course submission)
All P0 user stories accepted; `pytest -q` green on a clean clone; evaluation tables generated by `run_all`; demo script rehearsed; report filled only from `results/`.

## 6. Target Users and Personas

| Persona | Context | Needs | Success looks like |
|---|---|---|---|
| **Asha, viewer** | Evening, knows the mood, not the title | Plain English, exclusions respected, reasons | Picks a movie from the top 5 in under a minute |
| **Dr. Rao, examiner** | Viva, 10 minutes, Compiler Design lens | See lexing, parsing, semantics, IR, optimization, codegen; proofs of correctness | Every phase visible and defensible |
| **Keshore, developer** | Building one stage | Clear interfaces, golden files, fast tests | Change one module without breaking others |

## 7. User Stories and Acceptance Criteria

### US-1 · P0 — Ask in plain English
As a viewer, I want to type what I feel like watching, so that I don't have to translate it into filters.
- [ ] Any 1–300 character request is accepted (FR-01).
- [ ] Unknown words are used for semantic matching, not rejected (S101/WORD).
- [ ] Results appear with a title, year, genres and reasons.

### US-2 · P0 — Exclusions mean exclusions
As a viewer, I want "no horror" to remove horror films and "little romance" to only reduce romance, so that results respect how strongly I said it.
- [ ] "no X" (genre) compiles to a hard NOT_HAS constraint; no result has X.
- [ ] "little X", "not too X", "ideally no X" compile to soft penalties.
- [ ] "no gore" (no field to check) is applied softly with warning S106.

### US-3 · P0 — Numeric limits
As a viewer, I want "after 2010", "rated at least 4", "at least 100 ratings", "90s" to filter results.
- [ ] Field inferred from unit or value (S2); converted to canonical bounds (O2).
- [ ] Every result satisfies every hard bound; unknown values fail.

### US-4 · P0 — Honest about missing data
As a viewer, I want to be told when the system cannot apply a condition, so that I am not misled.
- [ ] "under 2 hours" shows S105 and is not applied.
- [ ] Contradictions (S107) and empty ranges (S108) stop with highlighted spans; nothing is executed.

### US-5 · P0 — Why this movie
As a viewer, I want each result to say why it was chosen.
- [ ] Reasons list matched genres, matched tags, satisfied conditions with actual values and any penalties.
- [ ] No reason without trace evidence.

### US-6 · P0 — See the compiler
As an examiner, I want to see tokens, AST, semantic annotations, IR before/after passes, plans before/after optimization, instructions and timings for any request.
- [ ] Compiler view tabs exist for each stage.
- [ ] Applied rules are listed with before/after.

### US-7 · P0 — Prove optimization is safe
As an examiner, I want proof that optimization does not change results.
- [ ] Optimizer toggle shows identical results with different timings.
- [ ] `test_equivalence.py` and `test_preservation.py` pass on the full benchmark.

### US-8 · P0 — Choose how many
As a viewer, I want "top 5" or "show me 3" to control the number of results.
- [ ] Limits 1–50; larger values clamped with S109.

### US-9 · P1 — Variety
As a viewer, I want "diverse" to avoid near-duplicates.
- [ ] With MMR built, diversity increases (measured) with bounded relevance loss.

### US-10 · P1 — Runtime and language
As a viewer, I want "under 2 hours" and "in Korean" to work.
- [ ] With TMDB enrichment loaded, the registry marks the fields available and S105 disappears.

### US-11 · P0 — Reproduce every number
As a developer, I want one command to regenerate all evaluation tables.
- [ ] `python -m cineverse.eval.run_all` writes every CSV and plot in `results/`.

## 8. Scope

### 8.1 In scope (v1.0)
Request language v1.0; lexer, parser, AST, registry, semantic analysis, diagnostics, IR, passes O1–O2, planner, optimizer O3–O4, codegen, executor, trace; Sentence-Transformer + FAISS retrieval, metadata and popularity ranking, RRF, hard/soft constraints, explanations; Streamlit app; tests; evaluation.

### 8.2 Out of scope
User-facing DSL; general NL understanding; LLMs; BM25; collaborative filtering (P1); FastAPI (P1); databases beyond optional SQLite feedback; Docker/cloud; accounts; mobile.

## 9. Functional Requirements

| Component | IDs | Summary |
|---|---|---|
| Driver and lexer | FR-01, FR-02 | Input limits; typed tokens with spans; lexicon precedence |
| Parser and AST | FR-03 | Recursive descent, panic-mode recovery |
| Registry and semantic analysis | FR-04, FR-05 | Symbol table from data; rules S1–S13; diagnostics |
| IR and passes | FR-06, FR-07 | Typed versioned IR; O2, O1 |
| Planner, optimizer, codegen | FR-08–FR-11 | Template plan; O3, O4; equivalence; SSA program |
| Executor and runtime | FR-12–FR-17 | Validation and failure policy; semantic, metadata, popularity; RRF; constraints; explanations |
| Trace, baseline, evaluation | FR-18–FR-20 | Trace schema; preservation; `run_all` |
| Interface | FR-21 (P0), FR-22–FR-25 (P1) | Streamlit; MMR; API; TMDB; feedback |

Full statements and verification methods are in the SRS §3.

## 10. Non-Functional Requirements

| Category | Requirement | Target |
|---|---|---|
| Performance | Compile time | p95 < 50 ms |
| Performance | End-to-end | p95 < 1.5 s (warm, CPU) |
| Correctness | Hard violations | 0 |
| Correctness | Equivalence / preservation | 100% / 100% |
| Determinism | Repeat runs | Byte-identical IR and results |
| Portability | OS | Windows, macOS, Linux; Python 3.11 |
| Offline | After setup | No network needed |
| Privacy | Personal data | None stored |

## 11. System Architecture and Tech Stack
Compiler (front end → middle end → back end) produces a program; the runtime executes it. Python 3.11, dataclasses + Pydantic v2, hand-written recursive-descent parser, pandas/NumPy/PyArrow, sentence-transformers (all-MiniLM-L6-v2), faiss-cpu (flat), Streamlit, pytest. See the Technical Deep-Dive and System Architecture and Design.

## 12. Data and Integration Requirements

### 12.1 Core data
| Data | Source | Use |
|---|---|---|
| Movies, genres, year | MovieLens `movies.csv` | Catalogue, registry, constraints |
| Ratings | `ratings.csv` | Mean rating, votes, Bayesian rating |
| Tags | `tags.csv` | Embedding text, descriptor matching, explanations |
| Links | `links.csv` | Future TMDB enrichment |

### 12.2 External integrations
| Integration | Required | Notes |
|---|---|---|
| Hugging Face model download | Once | Cached locally |
| GroupLens download | Once | Manual; terms respected |
| TMDB API | P1 only | Needs API key in `.env` |

## 13. UX and Interface Requirements
Single page: request box with examples; result cards (title, year, genres, score, reasons); diagnostics banner with span highlights; "Compiler view" with tabs Tokens · AST · Semantic · IR · Plan · Program · Timings · Trace; optimizer toggle. Detail in UI/UX and API Specification.

## 14. Assumptions, Constraints and Dependencies
- MovieLens snapshot pinned by checksum; runtime/language unavailable in CORE.
- CPU laptops; model fits in memory (~90 MB).
- One semester; three members.
- Depends on faiss-cpu wheels for Python 3.11 (NumPy backend as fallback).

## 15. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Panel sees the compiler as decoration | Medium | High | Real stages, golden files, equivalence proofs, demo of every tab |
| Parser coverage too narrow | Medium | Medium | Free-text fallback; grow lexicon from dev failures; report coverage |
| faiss-cpu install fails on a laptop | Low | Medium | NumPy backend, identical results |
| Sparse tags weaken semantic search | High | Medium | Titles + genres in text; metadata channel; report limitation |
| Optimizer bug changes results | Medium | High | One rule at a time; equivalence gate |
| Self-made relevance labels bias results | Medium | Medium | Blind pooling, two judges, κ |
| Scope creep (LLM, BM25, API) | Medium | High | REMOVE list; P1 only after P0 |

## 16. Success Metrics and KPIs

| Metric | Definition | Target |
|---|---|---|
| AST accuracy | Parsed AST = golden | ≥ 90% |
| IR exact match | Canonical IR = gold | ≥ 85% |
| Diagnostic accuracy | Correct codes on invalid set | ≥ 90% |
| Equivalence | Optimized = unoptimized | 100% |
| Preservation | Compiled = baseline | 100% |
| Hard violations | Results violating hard constraints | 0 |
| NDCG@10 | Graded relevance, pooled judgments | Reported vs B0, B1, B2 |
| Compile p95 | Lex → codegen | < 50 ms |

## 17. Release Plan and Timeline

| Milestone | Content | Exit |
|---|---|---|
| M1 Foundation | Steps 1–4: scope, env, data, runtime + baseline | Baseline answers specs |
| M2 Front end | Steps 5–7: lexer, parser, semantics, IR | Golden ASTs, S-rule tests |
| M3 Back end | Steps 8–9: planner, codegen, executor, preservation | Preservation 100% |
| M4 Optimizer | Step 10: O2, O1, O3, O4 | Equivalence 100% |
| M5 Product | Steps 11–12: scoring tuned, explanations, app | Demo checklist |
| M6 Evidence | Steps 13–14: evaluation, report, rehearsal | Verification checklist |

Map milestones to the course review dates once announced (see Project Control).

## 18. Team — Roles and Responsibilities

| Member | Primary ownership | Secondary |
|---|---|---|
| Member A | Front end: lexer, lexicon, parser, AST, registry, semantics, diagnostics | UI Compiler view |
| Member B | Middle/back end: IR, passes, planner, optimizer, codegen, equivalence | Executor, trace |
| Member C | Runtime and data: catalogue, embeddings, FAISS, metadata, fusion, scoring, explanations, baseline, evaluation | Streamlit results |

Assign names to A/B/C in Project Control.

## 19. Future Roadmap
TMDB enrichment (runtime, language, overview); MMR; "movies like *Title*"; multi-turn refinement as IR patches; approximate index with measured pushdown policy; multilingual requests.

## 20. Appendix — Glossary

| Term | Definition |
|---|---|
| Request language | The subset of English the parser understands structurally |
| Registry | Symbol table: fields, types, aliases, units, capabilities |
| IR | `CompiledQuery`, the typed meaning of a request |
| Plan | DAG of logical operators |
| Program | SSA three-address instructions |
| Hard / soft | Removes movies / changes score |
| Equivalence | Optimized and unoptimized results identical |
| Preservation | Compiled-unoptimized results equal the hand-wired baseline |
