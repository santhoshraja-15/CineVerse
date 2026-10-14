"""Spec: Optimizer and Equivalence Testing Specification §4, §4.1 (O3, O4)."""

from __future__ import annotations

import pytest

from cineverse.compiler.codegen import generate, print_program
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
APPROX = Capabilities(exact_search=False, semantic_available=True)
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


def test_o4_shared_mask(runtime_cfg):
    ir = q([COMEDY], [C("year", ">=", 2011)], "comedy")
    _, out, log = run(ir, runtime_cfg, rules=["O4"])
    assert log == ["O4: pushed MASK [year >= 2011] into a1, b1"]
    assert out.nodes["a1"].inputs == ["m1"] == out.nodes["b1"].inputs
    assert out.nodes["a1"].args["c"] == 200 and "a2" not in out.nodes


def test_o4_truncation_only_when_no_hard_predicates(runtime_cfg):
    ir = q([Preference(kind="text", value="heist", polarity=1)], text="heist")
    _, out, log = run(ir, runtime_cfg, rules=["O4"])
    assert log == ["O4: pushed truncation into a1, b1"] and "m1" not in out.nodes
    assert out.nodes["a1"].inputs == ["s0"]


def test_o4_negative_refuses_on_approximate_index(runtime_cfg):
    ir = q([COMEDY], [C("year", ">=", 2011)], "comedy")
    _, out, log = run(ir, runtime_cfg, caps=APPROX, rules=["O4"])
    assert log == [] and "a2" in out.nodes and out.nodes["a1"].args["c"] == "N"


def test_o3_then_o4_popularity_only(runtime_cfg):
    _, out, log = run(q(cons=[C("rating", ">=", 4.0), C("year", ">=", 2016)]), runtime_cfg)
    assert log[-1] == "O4: pushed MASK [rating >= 4.0, year >= 2016] into p1"
    assert print_program(generate(out)) == [
        "%s0 = SCAN", "%m1 = MASK %s0, [rating >= 4.0, year >= 2016]", "%p1 = POP_RANK %m1, c=200",
        "%f = RRF %p1, k=60", "%r = SOFT %f, prefs=[], soft=[]", "%t = TOPK %r, n=10",
        "%x = EXPLAIN %t", "RET %x"]


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
