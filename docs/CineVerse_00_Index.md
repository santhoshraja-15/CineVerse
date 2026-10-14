# CineVerse — Documentation Set Index
**Index · v1.0**

Team 14 (Santhoshraja S, Siddharth P, Keshore G) · 2026-10-14

---

CineVerse compiles natural-language movie requests into optimized, explainable hybrid recommendation plans. This archive is the complete documentation set for building, testing, demonstrating and defending it.

> **Which document wins.** The six **normative** specifications (marked N) define names, schemas, rules and formulas. If any other document disagrees with them, the normative specification wins. The Final Project Report is the academic write-up of the same design.

## Documents

| # | File | Kind | What it is for |
|---|---|---|---|
| 1 | `CineVerse_Final_Project_Report.docx` | Report | Course submission report (compiler-first), with diagram and viva Q&A |
| 2 | `CineVerse_Software_Requirements_Specification.md` | Requirements | FR/NFR with priorities, verification and owners; traceability |
| 3 | `CineVerse_System_Architecture_and_Design.md` | Design document | Architecture style, modules, interfaces, ADRs, quality scenarios |
| 4 | `CineVerse_Compiler_Frontend_Specification.md` | **N** | Request language, registry, lexer, grammar, parser, AST, semantic rules, diagnostics |
| 5 | `CineVerse_IR_and_Execution_Plan_Specification.md` | **N** | IR, lowering, serialisation, logical plan, instructions, executor |
| 6 | `CineVerse_Optimizer_and_Equivalence_Testing_Specification.md` | **N** | O1–O4, correctness arguments, preservation and equivalence gates |
| 7 | `CineVerse_Dataset_and_Data_Pipeline_Specification.md` | **N** | MovieLens, catalogue, prepare and index pipelines, checks |
| 8 | `CineVerse_Recommendation_Engine_Specification.md` | **N** | Runtime operators, scoring, explanations, baseline |
| 9 | `CineVerse_UI_UX_and_API_Specification.md` | Spec | Streamlit UI, Python API, optional HTTP API |
| 10 | `CineVerse_Testing_and_Quality_Assurance_Plan.md` | Plan | Test levels, inventory, golden files, gates |
| 11 | `CineVerse_Evaluation_and_Benchmarking_Plan.md` | Plan | Benchmark, judgments, systems, metrics, protocol |
| 12 | `CineVerse_Implementation_Roadmap_and_Task_Checklist.md` | Plan | 14 steps, tasks T01–T34, exit criteria |
| 13 | `CineVerse_Database_and_Data_Schemas.md` | **N** | Every stored format (Parquet, artifacts, manifest, benchmark, results, optional SQLite) |
| 14 | `CineVerse_Repository_Structure_and_Coding_Standards.md` | Standard | Repo tree, ownership, naming, conventions, Git workflow |
| 15 | `CineVerse_Environment_Setup_and_Dependencies.md` | Guide | Install on Windows/macOS/Linux, verification, troubleshooting |
| 16 | `CineVerse_Configuration_and_Secrets_Management.md` | Guide | YAML configs, env vars, the one optional secret |
| 17 | `CineVerse_Deployment_and_Runbook.md` | Runbook | Build, run, incident playbook, demo-day script, release |
| 18 | `CineVerse_Logging_Tracing_and_Observability.md` | Spec | Logging setup, trace schema, timings, debugging recipes |
| 19 | `CineVerse_Example_Requests_and_Expected_Outputs.json` | Test data | 25 requests with expected tokens, IR, diagnostics, programs, properties |
| 20 | `CineVerse_Claude_Code_Master_Instructions.md` | Build instructions + build prompt | Operating contract (CLAUDE.md), canonical specs, task prompts T01–T34 |
| 21 | `CineVerse_PRD.md` | PRD | Vision, personas, user stories, scope, KPIs, release plan |
| 22 | `CineVerse_Technical_Deep_Dive.md` | Technical deep dive | Thesis, topology, per-component deep dives, walkthrough |
| 23 | `CineVerse_Flow_Document.md` | Flows | Setup, compilation, execution, error, optimizer, evaluation, dev flows |
| 24 | `CineVerse_Project_Control.md` | Project control | Charter, RACI, milestones, change control, decisions, risks, gates |
| 25 | `CineVerse_Layer_Architecture_Requirements.md` | Requirements | Six layers, dependency rules, enforcement test |
| 26 | `CineVerse_Tech_Stack_Master_Prompt.md` | Prompt | Approved stack and the setup prompt for Claude Code |
| — | repository root | Files | `CLAUDE.md`, `config/`, `.env.example`, requirements files (originally shipped in `starter/`) |

## Reading paths
| Reader | Order |
|---|---|
| Faculty / examiner | 1 → 21 → 22 → 4 → 6 |
| New team member | 21 → 3 → 22 → 25 → 12 → 14 → 15 |
| Claude Code session | `CLAUDE.md` (repo root) → 20 → the task's cited normative spec |
| Demo preparation | 17 → 9 → 19 |

## Build in three commands (after setup)
```bash
python -m cineverse.data.prepare && python -m cineverse.data.build_index
pytest -q
streamlit run app/streamlit_app.py
```
