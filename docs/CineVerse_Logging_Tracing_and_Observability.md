# CineVerse — Logging, Tracing and Observability
**Logging, Tracing and Observability · v1.0**

Team 14 (Santhoshraja S, Siddharth P, Keshore G) · 2026-10-14 · Status: Draft for team review

---

> **Purpose.** Two mechanisms: **logs** (operational, human-readable, for developers) and **traces** (structured, one JSON per request, for the UI, tests and the viva). Traces are the primary observability tool; logs explain what happened around them.

## Contents
1. Principles · 2. Logging · 3. Execution Trace · 4. Timings and Metrics · 5. Debugging Recipes · 6. Privacy

## 1. Principles
- Every request produces a trace; every trace validates against `runtime/trace_schema.json`.
- Every stage and every instruction is timed.
- Logs never contain secrets; traces never contain personal data.
- Observability adds no randomness and does not change results.

## 2. Logging
| Item | Setting |
|---|---|
| Library | Python `logging`, configured once in `cineverse/logging_setup.py` |
| Handlers | Console (INFO) + rotating file `logs/cineverse.log` (DEBUG, 1 MB × 3) |
| Format | `%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s` |
| Level | `CINEVERSE_LOG_LEVEL` (default INFO) |
| Logger names | Module paths (`cineverse.compiler.parser`, …) |
| Request id | 12-hex id generated in `recommend()`, injected via `logging.LoggerAdapter` |

| Level | Use |
|---|---|
| DEBUG | Stage inputs/outputs sizes, rule precondition decisions |
| INFO | Request received, compile ok/failed with codes, execution done with ms |
| WARNING | X201 fallback, config overrides, golden mismatch in tests |
| ERROR | Unexpected exceptions (with request id; trace persisted) |

Compiler stages are pure and do not log; the driver logs around them.

## 3. Execution Trace
JSON object, `trace_version: "1.0"`: `source`, `tokens[]`, `ast`, `diagnostics[]`, `ir_lowered`, `ir`, `rule_log[]`, `plan_unoptimized`, `plan`, `program[]`, `execution[]` (per instruction), `results[]` (with evidence), `timings_ms` (lex, parse, analyse, lower, passes, plan, optimize, codegen, execute, total), `versions` (ir, registry, dataset checksum, model). A JSON Schema lives in `cineverse/runtime/trace_schema.json`.

### 3.1 JSON Schema (abridged; full file `runtime/trace_schema.json`)
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "CineVerse trace",
  "type": "object",
  "required": ["trace_version", "request_id", "source", "tokens", "ast", "diagnostics",
               "ir_lowered", "ir", "rule_log", "plan_unoptimized", "plan", "program",
               "execution", "results", "timings_ms", "versions"],
  "properties": {
    "trace_version": {"const": "1.0"},
    "request_id": {"type": "string", "pattern": "^[0-9a-f]{12}$"},
    "source": {"type": "string", "maxLength": 300},
    "tokens": {"type": "array", "items": {"type": "object",
               "required": ["type", "lexeme", "value", "span"]}},
    "ast": {"type": "object"},
    "diagnostics": {"type": "array", "items": {"type": "object",
               "required": ["code", "severity", "message"]}},
    "ir_lowered": {"type": ["object", "null"]},
    "ir": {"type": ["object", "null"]},
    "rule_log": {"type": "array", "items": {"type": "object",
               "required": ["rule", "level", "detail"]}},
    "plan_unoptimized": {"type": ["object", "null"]},
    "plan": {"type": ["object", "null"]},
    "program": {"type": "array", "items": {"type": "string"}},
    "execution": {"type": "array", "items": {"type": "object",
               "required": ["index", "opcode", "ms", "out_size", "status"]}},
    "results": {"type": "array", "items": {"type": "object",
               "required": ["movie_id", "title", "score", "reasons", "evidence"]}},
    "timings_ms": {"type": "object", "required": ["lex", "parse", "analyse", "total"]},
    "versions": {"type": "object", "required": ["ir", "registry", "dataset_sha256", "model"]}
  }
}
```

### 3.2 Persistence
Traces are kept in memory for the UI. With `CINEVERSE_PERSIST_TRACES=1` they are written to `traces/<request_id>.json`. Evaluation runs persist traces for failed or mismatching items only.

## 4. Timings and Metrics
| Measurement | Where | Unit |
|---|---|---|
| Stage times (lex, parse, analyse, lower, passes, plan, optimize, codegen) | `CompilationResult.timings_ms` | ms (perf_counter_ns / 1e6) |
| Instruction times | `trace.execution[].ms` | ms |
| Output sizes | `trace.execution[].out_size` | count |
| End-to-end | `timings_ms.total` | ms |
| Aggregates | `eval/latency.py` → `results/latency.csv` | p50, p95 |

No metrics server; aggregation happens offline in evaluation.

## 5. Debugging Recipes
| Question | Look at |
|---|---|
| Why was this word ignored? | Tokens tab: FILLER or P001 span |
| Why is a movie missing? | `execution` MASK out_size; result evidence of neighbours; hard predicates in IR |
| Why did a movie rank high? | `results[].evidence`: ranks per source, matches, penalties |
| Did an optimization change anything? | `rule_log`; run with `optimize=False`; `equivalence.check` |
| Why is it slow? | `execution[].ms` per opcode; cold vs warm |

## 6. Privacy
Requests are not linked to people; no IP, name or account is stored. Optional feedback stores request text, IR hash, movie id and verdict only. Secrets are masked by a logging filter (Configuration §6).
