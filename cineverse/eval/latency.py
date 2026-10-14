"""Latency: compiler stages and instructions, optimizer off and on, and the selectivity study.

Spec: CineVerse_Evaluation_and_Benchmarking_Plan §7; Optimizer Spec §9.
"""

from __future__ import annotations

import statistics
from typing import Any

import numpy as np

from cineverse.compiler.driver import compile_text
from cineverse.compiler.registry import DomainRegistry
from cineverse.eval.metrics import percentile
from cineverse.runtime.constraints import mask
from cineverse.runtime.context import RuntimeContext
from cineverse.runtime.executor import execute

STAGES = ("lex", "parse", "analyse", "lower", "passes", "plan", "optimize", "codegen")


def measure(
    items: list[dict[str, Any]],
    ctx: RuntimeContext,
    registry: DomainRegistry,
    *,
    compile_runs: int = 100,
    exec_runs: int = 20,
) -> list[dict[str, Any]]:
    """Rows of results/latency.csv: request_id, optimize, stage_or_opcode, run, ms.

    Each item is executed once untimed first (warm-up); then `exec_runs` timed runs per setting.
    """
    rows: list[dict[str, Any]] = []
    for item in items:
        if item["gold_ir"] is None:
            continue
        for optimize in (False, True):
            for run in range(compile_runs):
                comp = compile_text(item["text"], registry, ctx.cfg, optimize=optimize)
                total = 0.0
                for stage in STAGES:
                    ms = comp.timings_ms.get(stage, 0.0)
                    total += ms
                    rows.append({"request_id": item["id"], "optimize": optimize,
                                 "stage_or_opcode": stage, "run": run, "ms": round(ms, 4)})
                rows.append({"request_id": item["id"], "optimize": optimize,
                             "stage_or_opcode": "compile_total", "run": run,
                             "ms": round(total, 4)})
            comp = compile_text(item["text"], registry, ctx.cfg, optimize=optimize)
            execute(comp.program or [], ctx, ir=comp.ir)  # warm-up
            for run in range(exec_runs):
                exe = execute(comp.program or [], ctx, ir=comp.ir)
                for record in exe.execution:
                    rows.append({"request_id": item["id"], "optimize": optimize,
                                 "stage_or_opcode": record["opcode"], "run": run,
                                 "ms": round(record["ms"], 4)})
                rows.append({"request_id": item["id"], "optimize": optimize,
                             "stage_or_opcode": "execute_total", "run": run,
                             "ms": round(exe.ms, 4)})
    return rows


def selectivity(item: dict[str, Any], ctx: RuntimeContext, registry: DomainRegistry) -> float:
    """eligible / N for the request's hard constraints."""
    comp = compile_text(item["text"], registry, ctx.cfg)
    hard = [c for c in comp.ir.constraints if c.strictness == "hard"] if comp.ir else []
    n = len(ctx.catalog)
    return len(mask(ctx.catalog, ctx.catalog.all_ids(), hard)) / n if n else 0.0


def summarise(rows: list[dict[str, Any]], ctx: RuntimeContext, registry: DomainRegistry,
              items: list[dict[str, Any]]) -> dict[str, Any]:
    """p50/p95 of compile and execution, and median speed-up by selectivity group."""
    def values(key: str, optimize: bool) -> list[float]:
        return [r["ms"] for r in rows if r["stage_or_opcode"] == key and r["optimize"] == optimize]

    out: dict[str, Any] = {
        "compile_p50_ms": percentile(values("compile_total", True), 50),
        "compile_p95_ms": percentile(values("compile_total", True), 95),
        "execute_p50_ms_unoptimized": percentile(values("execute_total", False), 50),
        "execute_p95_ms_unoptimized": percentile(values("execute_total", False), 95),
        "execute_p50_ms_optimized": percentile(values("execute_total", True), 50),
        "execute_p95_ms_optimized": percentile(values("execute_total", True), 95),
    }
    groups: dict[str, list[float]] = {"<0.1": [], "0.1-0.5": [], ">0.5": []}
    for item in items:
        if item["gold_ir"] is None:
            continue
        per = {opt: statistics.median(r["ms"] for r in rows if r["request_id"] == item["id"]
                                      and r["stage_or_opcode"] == "execute_total"
                                      and r["optimize"] == opt) for opt in (False, True)}
        sel = selectivity(item, ctx, registry)
        group = "<0.1" if sel < 0.1 else "0.1-0.5" if sel <= 0.5 else ">0.5"
        groups[group].append(per[False] / per[True] if per[True] else float("nan"))
    for name, speedups in groups.items():
        out[f"speedup_median_selectivity_{name}"] = (
            float(np.median(speedups)) if speedups else float("nan"))
        out[f"items_selectivity_{name}"] = len(speedups)
    return out
