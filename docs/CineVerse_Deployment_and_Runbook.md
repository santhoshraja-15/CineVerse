# CineVerse — Deployment and Runbook
**Deployment and Runbook · v1.0**

Team 14 (Santhoshraja S, Siddharth P, Keshore G) · 2026-10-14 · Status: Draft for team review

---

> **Deployment model.** CineVerse runs locally on a team member's laptop (the demo machine). There is no server deployment in the CORE scope. This runbook covers building, running, demo-day operation, failure recovery and the final release checklist.

## Contents
1. Environments · 2. Build Procedure · 3. Run Procedure · 4. Operations Checks · 5. Incident Playbook · 6. Demo-Day Runbook · 7. Release Procedure · 8. Optional Hosting

## 1. Environments
| Environment | Machine | Purpose |
|---|---|---|
| Dev | Each member's laptop | Development and tests |
| Demo | One designated laptop + one backup laptop | Viva / review |
| Eval | Demo laptop (fixed hardware) | Final `run_all` numbers |

## 2. Build Procedure
| Step | Command | Success check |
|---|---|---|
| 1 | Create venv, install requirements (Environment Setup §3–4) | import check prints `ok` |
| 2 | `python -m cineverse.data.prepare` | `catalog.parquet` exists; manifest coverage printed |
| 3 | `python -m cineverse.data.build_index` | I5 self-retrieval check passes |
| 4 | `pytest -q` | all green |
| 5 | `python -m cineverse.eval.run_all` (Eval only) | `results/` regenerated; `run_manifest.json` written |

## 3. Run Procedure
```bash
source .venv/bin/activate            # Windows: .venv\Scripts\Activate.ps1
export HF_HUB_OFFLINE=1              # Windows: $env:HF_HUB_OFFLINE=1
streamlit run app/streamlit_app.py   # http://localhost:8501
```
Stop with Ctrl+C. Logs go to the terminal and `logs/cineverse.log` (Logging §2).

## 4. Operations Checks (before every demo or eval run)
- [ ] `git status` clean; on the tagged release commit.
- [ ] `artifacts/manifest.json` checksums equal those in `results/run_manifest.json`.
- [ ] `pytest -q -m "not full"` green (≈ 30 s).
- [ ] App footer shows catalogue rows, model and IR version.
- [ ] EX01 returns 5 results in < 2 s after warm-up.
- [ ] Laptop on power; sleep disabled; notifications off; network not required.

## 5. Incident Playbook
| Symptom | Likely cause | Action |
|---|---|---|
| Banner X201 "semantic search unavailable" | Index or model missing/corrupt | Run `build_index`; meanwhile demo continues metadata-only (explain X201 as a designed fallback) |
| App crashes on start | Config validation error | Read `ConfigError` key path; restore `config/` from Git |
| Results differ from rehearsal | Different snapshot or config | Compare manifest and config hashes; rebuild |
| Very slow first request | Model warm-up | Run one warm-up request before the audience arrives |
| Equivalence test fails | Optimizer bug | Do not demo the toggle; show the failing test as a caught bug; fix with a regression test |
| Laptop failure | Hardware | Switch to backup laptop (same tag, same artifacts copied) or the screen recording |

## 6. Demo-Day Runbook (≈ 8 minutes)
| # | Action | Narration point |
|---|---|---|
| 1 | Type EX01 | Plain English in, explained results out |
| 2 | Tokens tab | Longest match, spans, "sci-fi" one token |
| 3 | AST tab | Clauses without separators; LL(2) at HEDGE |
| 4 | Semantic tab | Field inference (2010 → year); hard vs soft |
| 5 | IR tab | O2 canonicalisation; IR hash |
| 6 | Plan tab | O4 shared MASK |
| 7 | Program + Timings | SSA program; time saved |
| 8 | Toggle optimizer | Same results, different time |
| 9 | "no romance" vs "little romance" | Hard removes, soft sinks |
| 10 | EX07 "comedy under 2 hours" | S105 honesty |
| 11 | EX08 "only horror and no horror" | S107, nothing executed |
| 12 | Terminal: `pytest -q tests/test_equivalence.py tests/test_preservation.py` | Proofs, not claims |

Backup materials: screenshots of each tab and a screen recording of the full script on a USB drive and in the team drive.

## 7. Release Procedure
1. All checklists in Testing Plan §9 complete.
2. Final `run_all` on the Eval machine; commit `results/`.
3. Update report tables from `results/`; regenerate the report document.
4. Tag `v1.0`; zip source (without data/artifacts) for submission.
5. Copy `artifacts/` and `data/processed/` to the backup laptop.

## 8. Optional Hosting (not required)
If a public demo is wanted later: Streamlit Community Cloud can host the app only if the dataset terms allow redistribution of derived artifacts; otherwise build the catalogue on start-up from the user's own download. Not part of the course scope.
