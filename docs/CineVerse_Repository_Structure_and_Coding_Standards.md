# CineVerse — Repository Structure and Coding Standards
**Repository Structure and Coding Standards · v1.0**

Team 14 (Santhoshraja S, Siddharth P, Keshore G) · 2026-10-14 · Status: Draft for team review

---

## Contents
1. Repository Tree · 2. File Ownership · 3. Naming · 4. Python Standards · 5. Compiler-Specific Conventions · 6. Testing Conventions · 7. Git Workflow · 8. Documentation Conventions · 9. Pre-Commit Checklist

## 1. Repository Tree (fixed)
```
cineverse/                       # repository root
├── CLAUDE.md                    # operating contract for Claude Code (from Master Instructions §A)
├── README.md
├── pyproject.toml               # ruff, pytest, mypy config; package metadata
├── requirements.txt             # direct dependencies (ranges)
├── requirements.lock            # pip freeze after Step 2
├── requirements-dev.txt         # pytest-cov, ruff, mypy, jsonschema
├── .env.example                 # only for OPTIONAL TMDB key
├── .gitignore
├── config/
│   ├── registry.yaml
│   └── runtime.yaml
├── cineverse/
│   ├── __init__.py              # recommend()
│   ├── config.py                # load + validate YAML into dataclasses
│   ├── logging_setup.py
│   ├── compiler/
│   │   ├── lexicon.py  lexer.py  ast.py  parser.py
│   │   ├── registry.py  semantic.py  diagnostics.py
│   │   ├── ir.py  passes.py  planner.py  optimizer.py
│   │   ├── codegen.py  equivalence.py  driver.py
│   ├── runtime/
│   │   ├── catalog.py  embeddings.py  semantic_index.py  metadata_search.py
│   │   ├── constraints.py  fusion.py  scoring.py  explain.py
│   │   ├── diversity.py         # OPTIONAL
│   │   ├── executor.py  trace.py  trace_schema.json  context.py
│   ├── baseline/  baseline.py  popularity.py
│   ├── data/      prepare.py  build_index.py  enrich_tmdb.py*
│   └── eval/      compiler_eval.py  rec_eval.py  latency.py  tune.py  run_all.py
├── app/streamlit_app.py
├── api/main.py*                 # OPTIONAL
├── storage/feedback.py*         # OPTIONAL
├── benchmark/  requests.jsonl  judgments.csv
├── data/       raw/  processed/       (git-ignored)
├── artifacts/                         (git-ignored)
├── traces/                            (git-ignored)
├── results/                           (final run committed)
├── docs/       CineVerse_*.md, CHANGELOG.md
├── scripts/    check.sh  check.ps1
└── tests/
    ├── conftest.py              # fixtures: toy_catalog, toy_embeddings, registry_toy, full_ctx
    ├── golden/  regenerate.py  tokens/  ast/  ir/  program/
    └── test_*.py
```

## 2. File Ownership
| Area | Owner | Reviewer |
|---|---|---|
| `compiler/{lexicon,lexer,ast,parser,registry,semantic,diagnostics}` | Member A | Member B |
| `compiler/{ir,passes,planner,optimizer,codegen,equivalence,driver}`, `runtime/{executor,trace}` | Member B | Member A |
| `runtime/*` (others), `data/*`, `baseline/*`, `eval/*` | Member C | Member B |
| `app/*` | Member C (results) + Member A (Compiler view) | Member B |
| `docs/*`, `benchmark/*` | All | Cross-review |

## 3. Naming
| Item | Convention | Example |
|---|---|---|
| Modules | snake_case, one stage per module | `semantic_index.py` |
| Classes | PascalCase | `CompiledQuery`, `RankedList` |
| Functions | snake_case verbs | `lex`, `parse`, `build_plan` |
| Constants | UPPER_SNAKE | `ALL_RULES` |
| Token types, opcodes | UPPER_SNAKE, exactly as spec | `NEG_SOFT`, `SEM_SEARCH` |
| Diagnostic codes | Letter + 3 digits, as spec | `S105` |
| Rules | `O1`–`O4` | — |
| Plan node ids / registers | `s0, m1, a1, a2, b1, b2, p1, p2, f, r, d, t, x` | `%m1` |
| Tests | `test_<module>.py::test_<behaviour>` | `test_lexer.py::test_not_too_is_soft` |

## 4. Python Standards
- Python 3.11; `from __future__ import annotations` in every module.
- Full type hints; `mypy` clean for `cineverse/compiler`.
- `ruff` (lint + format), line length 100.
- Dataclasses `frozen=True, slots=True` for AST, tokens, diagnostics, runtime records; Pydantic v2 frozen models for IR.
- No global mutable state; configuration passed explicitly (`RuntimeContext`, `DomainRegistry`).
- No `print`; use `logging` (see Logging document).
- Exceptions only for programming errors and unavailable resources (`IndexUnavailable`, `ModelUnavailable`); user-facing problems are `Diagnostic` values.
- Docstrings: one line stating the stage contract, plus `Spec: <document> §<n>`.

## 5. Compiler-Specific Conventions
- Stage functions are pure: `lex`, `parse`, `analyse`, `lower`, `run_ir_passes`, `build_plan`, `optimize`, `generate`.
- Every rule is a module-level object `Rule(id, level, precondition, apply)` registered in `ALL_RULES` in spec order.
- Every diagnostic message comes from the template table in `diagnostics.py`; no ad-hoc strings.
- Every AST node and IR element keeps its span.
- Sorting anywhere in ranking uses `rank_key(score, movie_id) = (-round(score, 6), movie_id)` from `runtime/fusion.py`.

## 6. Testing Conventions
- Arrange–act–assert; one behaviour per test; test name states the behaviour.
- Spec references in test docstrings (`"""Frontend Spec §6 S7."""`).
- Golden files regenerated only by `tests/golden/regenerate.py`.
- `@pytest.mark.full` for tests needing the real catalogue/index.

## 7. Git Workflow
- `main` always green. Feature branches `step-<n>/<task-id>-<slug>` (e.g. `step-5/T11-lexer`).
- One task per pull request; commit message `T11: lexer with longest match and spans`.
- Pull request template: task id, spec sections, tests added, golden diffs explained, checklist ticked.
- Reviewer from the ownership table; S1 defects block merge.
- Never commit `data/`, `artifacts/`, `traces/`, `.env`.

## 8. Documentation Conventions
- Specs are updated before code when an interface changes; record in `docs/CHANGELOG.md` with version bump.
- Report numbers only from `results/`.

## 9. Pre-Commit Checklist
- [ ] `ruff check . && ruff format --check .`
- [ ] `pytest -q -m "not full"` (and `pytest -q` when closing a step)
- [ ] Golden diffs reviewed
- [ ] Spec/CHANGELOG updated if an interface changed
- [ ] Only files named by the task were touched
