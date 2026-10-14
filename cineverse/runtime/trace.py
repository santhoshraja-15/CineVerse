"""Execution trace: one JSON document per request (trace_version 1.0).

The orchestration layer passes the compile-side parts already serialised, so the runtime never
imports the parser or AST modules (LR-2).
Spec: CineVerse_Logging_Tracing_and_Observability §3; Database and Data Schemas §6.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from cineverse.runtime.executor import ExecutionResult

TRACE_VERSION = "1.0"
SCHEMA_PATH = Path(__file__).with_name("trace_schema.json")


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, float) and value != value:  # NaN
        return None
    if hasattr(value, "item") and callable(value.item):  # numpy scalar
        return value.item()
    return value


def results_to_json(execution: ExecutionResult | None) -> list[dict[str, Any]]:
    if execution is None:
        return []
    return [_jsonable(asdict(r)) for r in execution.results]


def build_trace(
    request_id: str,
    compile_parts: dict[str, Any],
    execution: ExecutionResult | None,
    versions: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the trace; `compile_parts` comes from CompilationResult.to_trace_parts()."""
    diagnostics = list(compile_parts.get("diagnostics", []))
    timings = dict(compile_parts.get("timings_ms", {}))
    if execution is not None:
        diagnostics += [d.to_dict() for d in execution.diagnostics]
        timings["execute"] = execution.ms
    timings["total"] = sum(v for k, v in timings.items() if k != "total")
    trace = {
        "trace_version": TRACE_VERSION,
        "request_id": request_id,
        "source": compile_parts["source"],
        "tokens": compile_parts.get("tokens", []),
        "ast": compile_parts.get("ast", {}),
        "diagnostics": diagnostics,
        "ir_lowered": compile_parts.get("ir_lowered"),
        "ir": compile_parts.get("ir"),
        "rule_log": compile_parts.get("rule_log", []),
        "plan_unoptimized": compile_parts.get("plan_unoptimized"),
        "plan": compile_parts.get("plan"),
        "program": compile_parts.get("program", []),
        "execution": execution.execution if execution is not None else [],
        "results": results_to_json(execution),
        "timings_ms": timings,
        "versions": versions,
    }
    if execution is not None and execution.error:
        trace["error"] = execution.error
    return _jsonable(trace)  # type: ignore[no-any-return]


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def persist(trace: dict[str, Any], directory: Path) -> Path:
    """Write traces/<request_id>.json (only when CINEVERSE_PERSIST_TRACES=1)."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{trace['request_id']}.json"
    path.write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
