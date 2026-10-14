# CineVerse — Project Control Document
**Project Control Document · v1.0**

Team 14 (Santhoshraja S, Siddharth P, Keshore G) · 2026-10-14 · Status: Draft for team review

---

> **Purpose.** How the project is governed: who decides, how scope and specs change, how progress, risks and quality are tracked, and what is reported to the faculty. Fill the bracketed fields at the first team meeting.

## Contents
1. Project Charter · 2. Organisation and RACI · 3. Milestones and Schedule · 4. Status Reporting · 5. Change Control · 6. Decision Log · 7. Risk Register · 8. Issue and Defect Tracking · 9. Quality Gates · 10. Communication Plan · 11. Configuration Management · 12. Closure Criteria

## 1. Project Charter
| Item | Value |
|---|---|
| Project | CineVerse — compiling natural-language movie requests into optimized, explainable hybrid recommendation plans |
| Course | Compiler Design (VIT) — course project |
| Team | Team 14: Santhoshraja S (24BCE2367), Siddharth P (24BCE2544), Keshore G (24BCE0266) |
| Faculty guide | [name] |
| Objective | A working, tested compiler pipeline (lexer → codegen) executing on a hybrid movie recommender, with measured evaluation |
| In scope / out of scope | SRS §1.2 |
| Success criteria | SRS §8; PRD §5 |
| Constraints | One semester, CPU laptops, MovieLens latest-small, no paid services |

## 2. Organisation and RACI
| Role | Member |
|---|---|
| Member A — Front-end lead | [name] |
| Member B — Middle/back-end lead, integration owner | [name] |
| Member C — Runtime, data and evaluation lead | [name] |
| Scribe / document owner (rotating monthly) | [name] |

| Activity | A | B | C | Faculty |
|---|---|---|---|---|
| Request language and grammar | R/A | C | C | I |
| Semantic rules and diagnostics | R/A | C | I | I |
| IR, planner, optimizer, codegen | C | R/A | C | I |
| Runtime operators, data, baseline | I | C | R/A | I |
| Equivalence and preservation gates | C | R/A | C | I |
| Benchmark and judgments | R | R | R/A | I |
| UI | R (Compiler view) | C | R/A (results) | I |
| Report and viva | R | R | R | A (assessment) |

R responsible · A accountable · C consulted · I informed.

## 3. Milestones and Schedule
| Milestone | Content | Planned date | Review | Status |
|---|---|---|---|---|
| M1 Foundation | Steps 1–4 | [date] | — | Not started |
| M2 Front end | Steps 5–7 | [date] | [Review 1] | Not started |
| M3 Back end | Steps 8–9 | [date] | — | Not started |
| M4 Optimizer | Step 10 | [date] | [Review 2] | Not started |
| M5 Product | Steps 11–12 | [date] | — | Not started |
| M6 Evidence | Steps 13–14 | [date] | [Final review] | Not started |

Map dates to the course's review schedule once announced. Status values: Not started · In progress · Blocked · Done.

## 4. Status Reporting
Weekly status (Friday), stored in `docs/status/YYYY-MM-DD.md`:
```
Week: …   Milestone: …   Overall: Green / Amber / Red
Done this week: T.., T..
Planned next week: T.., T..
Test status: pytest N passed / M failed; gates: preservation __%, equivalence __%
Risks changed: R.. (↑/↓)
Decisions needed: …
```
Green = on plan; Amber = ≤ 1 week slip or one gate failing; Red = > 1 week slip or a P0 requirement at risk.

## 5. Change Control
| Change type | Example | Approval | Required updates |
|---|---|---|---|
| Spec change (language, IR, rules, opcodes) | Add a token type | All three members | Spec + CHANGELOG + version bump + golden regeneration review |
| Scope change (CORE ↔ OPTIONAL) | Promote MMR | All three + faculty informed | SRS priorities, PRD scope, Roadmap |
| Config freeze change | Re-tune weights | All three | Decision log; rerun evaluation |
| Code within a task | Lexer refactor | Reviewer | Tests |

Change request template: id, description, reason, affected documents/modules, risk, decision, date.

## 6. Decision Log
| ID | Date | Decision | Alternatives | Rationale | Owner |
|---|---|---|---|---|---|
| D-01 | 2026-10-13 | Compiler-first redesign; recommender is the target runtime | Recommender-first | Course is Compiler Design | Team |
| D-02 | 2026-10-13 | Project name CineVerse | Sentence2Movie | Team choice | Team |
| D-03 | 2026-10-13 | Remove BM25; metadata tag matching covers keywords | Keep BM25 | Short MovieLens text; duplication | Team |
| D-04 | 2026-10-13 | No LLM components | LLM parser | Determinism; equivalence testing | Team |
| D-05 | 2026-10-13 | Hand-written recursive-descent parser | PLY/ANTLR | Small grammar; spans; recovery | Team |
| D-06 | 2026-10-14 | Optional separators; HEDGE+NEG_HARD; OR in preferences; S114 | Strict SEP grammar | Real requests omit commas | Team |
| D-07 | 2026-10-14 | PopularityRank source for requests without positive preferences | S111 error | "no romance" must return results | Team |
| D-08 | 2026-10-14 | Exact search only in CORE | HNSW | Makes O4 provably safe | Team |

## 7. Risk Register
| ID | Risk | Likelihood | Impact | Owner | Mitigation | Trigger |
|---|---|---|---|---|---|---|
| R1 | Compiler seen as decoration | M | H | B | Real stages, golden files, proofs, demo | Reviewer comment |
| R2 | Parser coverage too narrow | M | M | A | Free-text fallback; lexicon growth from dev failures | Dev IR accuracy < 80% |
| R3 | faiss-cpu install failure | L | M | C | NumPy backend | Import error |
| R4 | Optimizer changes results | M | H | B | One rule at a time; equivalence gate | Any equivalence failure |
| R5 | Sparse tags weaken retrieval | H | M | C | Title+genre text; report coverage | Low dev NDCG |
| R6 | Schedule slip | M | H | All | P0 first; weekly status; cut P1 | Amber two weeks |
| R7 | Evaluation bias | M | M | C | Blind pooling, κ, cross-authoring | κ < 0.4 |
| R8 | Demo-day failure | L | H | B | Backup laptop, recording, offline run | Ops check fails |
| R9 | Member unavailable | M | M | All | Ownership + reviewer pairs; docs | > 1 week absence |

## 8. Issue and Defect Tracking
GitHub Issues with labels: `task`, `bug-S1`, `bug-S2`, `bug-S3`, `spec-change`, `risk`, `question`. Every bug includes request text, expected vs actual, stage, and trace. S1 bugs block merges (Testing Plan §8).

## 9. Quality Gates
| Gate | Criteria | When |
|---|---|---|
| G1 Spec sign-off | Specs v1.0 reviewed by all | End of step 1 |
| G2 Front-end | Golden ASTs + S-rule tests green | End of step 7 |
| G3 Preservation | 100% | End of step 9 |
| G4 Equivalence | 100% | End of step 10 |
| G5 Product | Example JSON test + UI checklist | End of step 12 |
| G6 Release | Testing Plan §9 + Runbook §4 | End of step 14 |

## 10. Communication Plan
| What | Channel | Frequency |
|---|---|---|
| Daily progress | Team chat | Daily |
| Status report | `docs/status/` | Weekly |
| Design decisions | Decision log | As needed |
| Faculty update | Email / review meeting | Per review |
| Code review | Pull requests | Per task |

## 11. Configuration Management
Git (main + task branches); tags per milestone (`m1`…`m6`, `v1.0`); data and artifacts reproducible from scripts with checksums in manifests; documents versioned in `docs/CHANGELOG.md`.

## 12. Closure Criteria
All P0 requirements verified; G1–G6 passed; report submitted with numbers from `results/`; repository tagged `v1.0`; lessons learned recorded in `docs/status/closure.md`.
