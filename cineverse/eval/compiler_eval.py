"""Compiler metrics: token/AST accuracy, IR exact match, slot P/R/F1, diagnostic precision and
recall, round trip, plan/program validity.

Spec: CineVerse_Evaluation_and_Benchmarking_Plan §5.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cineverse.compiler.ast import to_dict
from cineverse.compiler.driver import compile_text
from cineverse.compiler.ir import CompiledQuery
from cineverse.compiler.registry import DomainRegistry
from cineverse.config import RuntimeConfig
from cineverse.eval.metrics import micro_f1, prf
from cineverse.runtime.executor import validate as validate_program

TARGETS = {"ast_accuracy": 0.90, "ir_exact_match": 0.85, "diagnostic_precision": 0.90,
           "diagnostic_recall": 0.90, "round_trip": 1.0, "plan_validity": 1.0,
           "program_validity": 1.0}


def canonical(ir: CompiledQuery) -> dict[str, Any]:
    data = json.loads(ir.to_json())
    for key in ("source", "diagnostics"):
        data.pop(key)
    for c in data["constraints"]:
        c.pop("span")
    return data


def slots(ir: dict[str, Any]) -> set[object]:
    out: set[object] = {("pref", p["kind"], p["value"], p["polarity"]) for p in ir["preferences"]}
    out |= {("con", c["field"], c["op"], str(c["value"]), c["strictness"])
            for c in ir["constraints"]}
    out.add(("limit", ir["output"]["limit"]))
    return out


def evaluate(
    items: list[dict[str, Any]],
    registry: DomainRegistry,
    cfg: RuntimeConfig,
    golden_ast_dir: Path | None = None,
    examples: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Rows of results/compiler_metrics.csv (metric, split, value, n, target, passed)."""
    rows: list[dict[str, Any]] = []
    by_split: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        by_split.setdefault(item["split"], []).append(item)
    by_split["all"] = items

    def add(metric: str, split: str, value: float, n: int) -> None:
        target = TARGETS.get(metric)
        rows.append({"metric": metric, "split": split, "value": round(value, 4), "n": n,
                     "target": "" if target is None else target,
                     "passed": "" if target is None else value >= target})

    for split, group in by_split.items():
        valid = [i for i in group if i["gold_ir"] is not None]
        invalid = [i for i in group if i["gold_ir"] is None]
        comps = {i["id"]: compile_text(i["text"], registry, cfg) for i in group}

        exact, slot_counts, round_trip, plan_ok, prog_ok, ast_ok, ast_n = 0, [], 0, 0, 0, 0, 0
        for item in valid:
            comp = comps[item["id"]]
            if comp.ok and comp.ir is not None:
                got = canonical(comp.ir)
                exact += got == item["gold_ir"]
                slot_counts.append(prf(slots(got), slots(item["gold_ir"])))
                round_trip += CompiledQuery.from_json(comp.ir.to_json()) == comp.ir
                plan_ok += (comp.plan_unoptimized.validate() == []  # type: ignore[union-attr]
                            and comp.plan.validate() == [])  # type: ignore[union-attr]
                prog_ok += validate_program(comp.program or []) == []
            else:
                slot_counts.append(prf(set(), slots(item["gold_ir"])))
            golden = golden_ast_dir / f"{item['id']}.json" if golden_ast_dir else None
            if golden is not None and golden.is_file() and comp.ast is not None:
                ast_n += 1
                ast_ok += json.loads(golden.read_text("utf-8"))["ast"] == to_dict(comp.ast)
        n = len(valid)
        if n:
            add("ir_exact_match", split, exact / n, n)
            p, r, f = micro_f1(slot_counts)
            add("slot_precision", split, p, n)
            add("slot_recall", split, r, n)
            add("slot_f1", split, f, n)
            add("round_trip", split, round_trip / n, n)
            add("plan_validity", split, plan_ok / n, n)
            add("program_validity", split, prog_ok / n, n)
        if ast_n:
            add("ast_accuracy", split, ast_ok / ast_n, ast_n)
        if invalid:
            counts = [prf({d.code for d in comps[i["id"]].diagnostics}, set(i["gold_diagnostics"]))
                      for i in invalid]
            p, r, _ = micro_f1(counts)
            add("diagnostic_precision", split, p, len(invalid))
            add("diagnostic_recall", split, r, len(invalid))

    if examples:
        ok = sum(
            [t.display() for t in compile_text(e["text"], registry, cfg).tokens]
            == e["expected"]["tokens"] for e in examples
        )
        add("token_accuracy", "examples", ok / len(examples), len(examples))
    return rows
