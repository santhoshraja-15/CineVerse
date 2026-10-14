# CineVerse — Layer Architecture Requirements
**Layer Architecture Requirements · v1.0**

Team 14 (Santhoshraja S, Siddharth P, Keshore G) · 2026-10-14 · Status: Draft for team review

---

> **Purpose.** Defines the six layers, what each may and may not do, which layers it may import, and how the rules are enforced automatically. A change that breaks a layer rule fails the test suite.

## 1. Layers

| # | Layer | Packages | Responsibility | Owns data structures |
|---|---|---|---|---|
| L6 | Presentation | `app/`, `api/`* | Collect input, render results, diagnostics and trace | none |
| L5 | Orchestration | `cineverse/__init__.py` (`recommend`), `compiler/driver.py`, `eval/` | Wire stages, time them, choose optimize on/off | `CompilationResult` |
| L4 | Compiler | `compiler/` (lexicon, lexer, parser, ast, registry, semantic, diagnostics, ir, passes, planner, optimizer, codegen, equivalence) | Text → program; diagnostics; rule log | `Token`, AST nodes, `Annotation`, `Diagnostic`, `RuleApplication` |
| L3 | Contract | `compiler/ir.py`, `compiler/planner.py` (types), `compiler/codegen.py` (`Instruction`) | The only shapes that cross from compiler to runtime | `CompiledQuery`, `LogicalPlan`, `PlanNode`, `Instruction` |
| L2 | Runtime | `runtime/` (executor, trace, catalog, embeddings, semantic_index, metadata_search, constraints, fusion, scoring, explain, diversity*) | Execute programs; produce results and evidence | `RankedList`, `Recommendation`, `RuntimeContext`, trace |
| L1 | Data | `data/`, files under `data/`, `artifacts/`, `config/` | Build and load catalogue, index, configs | parquet, npy, FAISS, YAML, manifest |

`baseline/` sits beside the compiler at L4-equivalent level but may import **only** L2 and L1 (it must not use the compiler, so it can serve as an independent reference).

## 2. Dependency rules

| From \ May import | L6 | L5 | L4 | L3 | L2 | L1 |
|---|---|---|---|---|---|---|
| L6 Presentation | — | ✓ | ✗ | ✓ (types only, for rendering) | ✗ | ✗ |
| L5 Orchestration | ✗ | — | ✓ | ✓ | ✓ | ✓ |
| L4 Compiler | ✗ | ✗ | — | ✓ | ✗ | ✓ (registry reads config + catalogue stats) |
| L3 Contract | ✗ | ✗ | ✗ | — | ✗ | ✗ |
| L2 Runtime | ✗ | ✗ | ✗ | ✓ | — | ✓ |
| L1 Data | ✗ | ✗ | ✗ | ✗ | ✗ | — |
| baseline | ✗ | ✗ | ✗ | ✓ (IR types for specs) | ✓ | ✓ |

Hard rules:
- **LR-1** Compiler (L4) never imports `cineverse.runtime`.
- **LR-2** Runtime (L2) never imports lexer, parser, ast, semantic, passes or optimizer.
- **LR-3** Contract modules (L3) import only the standard library and Pydantic.
- **LR-4** Presentation never calls compiler stages directly; it calls `cineverse.recommend` or the driver.
- **LR-5** `baseline` never imports `cineverse.compiler` except IR type definitions.
- **LR-6** No layer reads raw CSV except `data/prepare.py`.
- **LR-7** Configuration values are read only through `config` loaders; no constants duplicated in code.

## 3. Per-layer requirements

| ID | Layer | Requirement |
|---|---|---|
| LA-01 | L6 | Must render diagnostics with spans and never hide WARNINGs |
| LA-02 | L6 | Must not compute scores or filter results |
| LA-03 | L5 | Must time every stage and every instruction and place timings in the trace |
| LA-04 | L5 | Must stop before planning on any ERROR |
| LA-05 | L4 | Every stage is a pure function of its inputs (no I/O, no globals, no randomness) |
| LA-06 | L4 | Every stage returns diagnostics as values |
| LA-07 | L4 | Optimizer rules have explicit precondition functions and log every application |
| LA-08 | L3 | IR and plan are immutable after construction; changes create new objects |
| LA-09 | L3 | IR carries `ir_version`; plan nodes carry operator names from the spec's closed set |
| LA-10 | L2 | Every ranking sorts by `(-round(score, 6), movie_id)` |
| LA-11 | L2 | Hard predicates only in MASK/FILTER_LIST; soft only in SOFT |
| LA-12 | L2 | Every operator adds evidence for the movies it outputs |
| LA-13 | L1 | All artifacts recorded in `artifacts/manifest.json` with checksums and versions |
| LA-14 | L1 | Raw files are never modified |

## 4. Enforcement

`tests/test_layers.py` parses every module's imports with `ast` and fails on any forbidden edge:

```python
FORBIDDEN = {
    "cineverse.compiler": ["cineverse.runtime", "cineverse.baseline", "streamlit"],
    "cineverse.runtime": ["cineverse.compiler.lexer", "cineverse.compiler.parser",
                          "cineverse.compiler.ast", "cineverse.compiler.semantic",
                          "cineverse.compiler.passes", "cineverse.compiler.optimizer",
                          "streamlit"],
    "cineverse.baseline": ["cineverse.compiler.lexer", "cineverse.compiler.parser",
                           "cineverse.compiler.semantic", "cineverse.compiler.passes",
                           "cineverse.compiler.optimizer", "cineverse.compiler.planner"],
    "app": ["cineverse.compiler.lexer", "cineverse.compiler.parser",
            "cineverse.runtime.fusion", "cineverse.runtime.scoring"],
}
# For each .py under the package, collect `import x` / `from x import y`
# and assert no import starts with a forbidden prefix for that module's package.
```

Purity (LA-05) is checked by a test that runs each compiler stage twice on the same input and compares outputs, and by a grep test forbidding `open(`, `random`, `time.` and `os.environ` in `cineverse/compiler/` (except `registry.py` loading and `driver.py` timing).

## 5. Rationale
The rules make the compiler testable without a model or index, keep the runtime ignorant of English, and make the baseline a genuinely independent reference for the preservation proof.
