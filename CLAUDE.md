# CLAUDE.md — CineVerse operating contract

## What CineVerse is
A Compiler Design course project. It compiles a natural-language movie request
(lexer → parser → AST → semantic analysis → typed IR → IR passes → logical plan →
optimizer → SSA instructions) and executes the program on a hybrid recommendation
runtime (Sentence Transformers + FAISS, metadata and popularity ranking, RRF, hard and
soft constraints, evidence-based explanations). The compiler is the main deliverable.

## GROUND TRUTH (never change without an explicit instruction)
- Normative specs in docs/: Compiler_Frontend, IR_and_Execution_Plan, Optimizer_and_
  Equivalence_Testing, Recommendation_Engine, Dataset_and_Data_Pipeline,
  Database_and_Data_Schemas. Names, codes, opcodes, schemas and formulas come from them.
- Package layout and layer rules: docs/CineVerse_Repository_Structure_and_Coding_Standards.md
  and docs/CineVerse_Layer_Architecture_Requirements.md.
- cineverse.compiler never imports cineverse.runtime; cineverse.runtime never imports the
  lexer, parser, ast, semantic, passes or optimizer. They meet only at CompiledQuery,
  LogicalPlan and list[Instruction].
- Task order: docs/CineVerse_Implementation_Roadmap_and_Task_Checklist.md.

## ANTI-HALLUCINATION RULES (hard)
1. Never invent a module, class, function, field, token type, diagnostic code, opcode or
   rule id. If the spec does not define it, stop and ask one question.
2. Before using any third-party API (sentence-transformers, faiss, pydantic, pandas,
   pyarrow, streamlit), read the installed package's docs or source in this session and
   use only signatures you have confirmed. Never guess call shapes from memory.
3. Never add a dependency that is not in requirements.txt / requirements-dev.txt.
4. Import existing types; never redefine a type that already exists in the codebase.
5. Never fabricate output: no hand-typed metrics, no invented movie titles in fixtures
   except the documented toy catalogue, no claimed results without a run.

## ANTI-DRIFT RULES (hard)
1. Touch only the files the current task lists.
2. No refactors, renames or "improvements" outside the task.
3. Keep data models byte-aligned with the normative specs (field names, enums, order).
4. Do not implement OPTIONAL features (MMR, TMDB, FastAPI, SQLite feedback, HNSW)
   unless the task says so.
5. Do not write optimizer code (O1–O4) before T21 (behaviour preservation) passes.
6. Golden files are regenerated only by tests/golden/regenerate.py and every diff is
   reported.

## QUALITY GATES
- Python 3.11, type hints everywhere, `from __future__ import annotations`.
- ruff clean; mypy clean for cineverse/compiler.
- Compiler stages are pure functions; user problems are Diagnostic values, not exceptions.
- Every ranking sorts by (-round(score, 6), movie_id).
- INVIOLABLE INVARIANT: an optimization never changes results; hard constraints act
  only in MASK/FILTER_LIST and an unknown value never satisfies a hard constraint.

## WORKING METHOD
1. Read the task, then the spec sections it cites.
2. State a short plan (files, functions, tests).
3. Write the tests first, then the code.
4. Run the task's VERIFY commands; paste the output.
5. Update docs/CHANGELOG.md if an interface changed (only when the task allows it).
6. One commit per task: "Txx: <summary>".

## DEFINITION OF DONE (per task)
VERIFY passes; `pytest -q -m "not full"` green; ruff clean; only allowed files changed;
the task's checkbox ticked in the Roadmap.
