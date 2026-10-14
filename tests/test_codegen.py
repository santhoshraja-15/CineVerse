"""Spec: IR and Execution Plan Specification §6, §8."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cineverse.compiler.codegen import Instruction, generate, print_program, topological
from cineverse.compiler.ir import CompiledQuery
from cineverse.compiler.planner import build_plan

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = [
    e for e in json.loads(
        (ROOT / "docs" / "CineVerse_Example_Requests_and_Expected_Outputs.json").read_text("utf-8")
    )["examples"] if e["expected"]["ok"]
]


def gold_ir(ex) -> CompiledQuery:
    gold = ex["expected"]["ir"]
    return CompiledQuery.model_validate(
        dict(gold, diagnostics=[], constraints=[dict(c, span=(0, 0)) for c in gold["constraints"]])
    )


@pytest.mark.parametrize("ex", EXAMPLES, ids=[e["id"] for e in EXAMPLES])
def test_unoptimized_program_printed_form_matches_example(ex, runtime_cfg):
    """The canonical plan from the gold IR prints exactly `program_unoptimized`."""
    program = generate(build_plan(gold_ir(ex), runtime_cfg))
    assert print_program(program) == ex["expected"]["program_unoptimized"]


def test_topological_order_breaks_ties_by_id(runtime_cfg):
    plan = build_plan(gold_ir(next(e for e in EXAMPLES if e["id"] == "EX03")), runtime_cfg)
    assert topological(plan) == ["s0", "a1", "a2", "b1", "b2", "p1", "p2", "f", "r", "t", "x"]


def test_ssa_each_register_assigned_once(runtime_cfg):
    for ex in EXAMPLES:
        dests = [i.dest for i in generate(build_plan(gold_ir(ex), runtime_cfg)) if i.dest]
        assert len(dests) == len(set(dests))


def test_program_ends_with_ret_of_sink(runtime_cfg):
    program = generate(build_plan(gold_ir(EXAMPLES[0]), runtime_cfg))
    assert program[-1] == Instruction(None, "RET", ("%x",))


def test_operands_are_registers_or_literals(runtime_cfg):
    program = generate(build_plan(gold_ir(EXAMPLES[0]), runtime_cfg))
    sem = next(i for i in program if i.opcode == "SEM_SEARCH")
    assert sem.operands == ("thoughtful science fiction mystery", "%s0", "N")
    assert str(sem) == '%a1 = SEM_SEARCH "thoughtful science fiction mystery", %s0, c=N'
