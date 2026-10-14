"""Spec: Optimizer and Equivalence Testing Specification §4, §4.1 (O3, O4)."""

from __future__ import annotations

import pytest

from cineverse.compiler.ir import (
    Capabilities,
    Channels,
    CompiledQuery,
    Constraint,
    Output,
    Preference,
)
from cineverse.compiler.optimizer import optimize
from cineverse.compiler.planner import build_plan

EXACT = Capabilities(exact_search=True, semantic_available=True)
COMEDY = Preference(kind="genre", value="Comedy", polarity=1)


def C(field, op, value, strictness="hard"):
    return Constraint(field=field, op=op, value=value, strictness=strictness, span=(0, 0))


def q(prefs=(), cons=(), text="", **kw) -> CompiledQuery:
    return CompiledQuery(source="s", semantic_text=text, preferences=list(prefs),
                         constraints=list(cons), channels=Channels(semantic=True), **kw)


def run(ir, cfg, caps=EXACT, rules=("O3", "O4")):
    plan = build_plan(ir, cfg)
    out, log = optimize(plan, ir, caps, set(rules))
    assert out.validate() == []
    return plan, out, [r.display() for r in log]


def test_o3_removes_both_empty_searches(runtime_cfg):
    plan, out, log = run(q(cons=[C("genre", "NOT_HAS", "Romance")]), runtime_cfg, rules=["O3"])
    assert log == ["O3: removed a1 (SemanticSearch) and a2",
                   "O3: removed b1 (MetadataSearch) and b2"]
    assert out.nodes["f"].inputs == ["p2"] and "a1" in plan.nodes  # original kept


def test_o3_negative_does_not_fire_with_positives(runtime_cfg):
    _, _, log = run(q([Preference(kind="genre", value="Comedy", polarity=1)], text="comedy"),
                    runtime_cfg, rules=["O3"])
    assert log == []


def test_o3_removes_unused_nodes(runtime_cfg):
    ir = q([Preference(kind="genre", value="Comedy", polarity=1)], text="comedy")
    plan = build_plan(ir, runtime_cfg)
    plan.add("z", "TopK", ["r"], n=3)  # reaches no sink
    out, log = optimize(plan, ir, EXACT, {"O3"})
    assert "z" not in out.nodes and log[0].display() == "O3: removed unused z"






def test_disabled_rules_leave_plan_unchanged(runtime_cfg):
    ir = q(cons=[C("genre", "NOT_HAS", "Romance")])
    plan = build_plan(ir, runtime_cfg)
    out, log = optimize(plan, ir, EXACT, set())
    assert log == [] and out.to_dict() == plan.to_dict()


@pytest.mark.parametrize("explain", [True, False])
def test_optimized_plan_valid_with_and_without_explain(runtime_cfg, explain):
    ir = q([Preference(kind="genre", value="Drama", polarity=1)], [C("year", ">=", 2000)], "drama",
           output=Output(explain=explain))
    run(ir, runtime_cfg)
