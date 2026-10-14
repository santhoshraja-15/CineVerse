"""Spec: IR and Execution Plan Specification §4, §5, §8."""

from __future__ import annotations

import pytest

from cineverse.compiler.ir import Channels, CompiledQuery, Constraint, Output, Preference, Ranking
from cineverse.compiler.planner import LogicalPlan, build_plan, positives


def C(field, op, value, strictness="hard"):
    return Constraint(field=field, op=op, value=value, strictness=strictness, span=(0, 0))


def P(kind, value, polarity=1):
    return Preference(kind=kind, value=value, polarity=polarity)


def ir(prefs=(), cons=(), text="", semantic=True, **kw) -> CompiledQuery:
    return CompiledQuery(source="s", semantic_text=text, preferences=list(prefs),
                         constraints=list(cons), channels=Channels(semantic=semantic), **kw)


def test_positives_only_template(runtime_cfg):
    plan = build_plan(ir([P("genre", "Comedy")], [C("year", ">=", 2000)], "comedy"), runtime_cfg)
    assert list(plan.nodes) == ["s0", "a1", "a2", "b1", "b2", "f", "r", "t", "x"]
    assert plan.nodes["f"].inputs == ["a2", "b2"] and plan.sink == "x"
    assert plan.nodes["a1"].args["c"] == "N" and plan.nodes["a2"].args["c"] == 200
    assert plan.validate() == []


def test_no_positives_adds_popularity(runtime_cfg):
    plan = build_plan(ir(cons=[C("genre", "NOT_HAS", "Romance")]), runtime_cfg)
    assert plan.nodes["f"].inputs == ["a2", "b2", "p2"] and plan.validate() == []


def test_negative_only_preferences_still_no_positives(runtime_cfg):
    plan = build_plan(ir([P("text", "gore", -1)]), runtime_cfg)
    assert "p1" in plan.nodes


def test_semantic_unavailable_omits_a1_a2(runtime_cfg):
    plan = build_plan(ir([P("genre", "Comedy")], semantic=False), runtime_cfg)
    assert "a1" not in plan.nodes and plan.nodes["f"].inputs == ["b2"]


def test_mmr_adds_diversify(runtime_cfg):
    plan = build_plan(ir([P("genre", "Comedy")], ranking=Ranking(diversity="mmr")), runtime_cfg)
    assert plan.nodes["t"].inputs == ["d"] and plan.nodes["d"].args["n"] == 10


def test_explain_false_sink_is_topk(runtime_cfg):
    plan = build_plan(ir([P("genre", "Comedy")], output=Output(explain=False)), runtime_cfg)
    assert plan.sink == "t" and "x" not in plan.nodes and plan.validate() == []


def test_hard_in_filters_soft_in_softscore(runtime_cfg):
    q = ir([P("genre", "Drama")], [C("year", ">=", 2000), C("votes", ">=", 10, "soft")])
    plan = build_plan(q, runtime_cfg)
    assert [c.field for c in plan.nodes["b2"].args["preds"]] == ["year"]
    assert [c.field for c in plan.nodes["r"].args["soft"]] == ["votes"]


def test_pos_genres_include_hard_has_and_are_sorted():
    genres, terms = positives(ir([P("genre", "Mystery"), P("text", "dark"), P("text", "b")],
                                 [C("genre", "HAS", "Comedy")]))
    assert genres == ["Comedy", "Mystery"] and terms == ["b", "dark"]


# --------------------------------------------------------------------------- validation rules


def bad_plan(runtime_cfg) -> LogicalPlan:
    return build_plan(ir([P("genre", "Comedy")]), runtime_cfg)


def test_rule1_two_sinks(runtime_cfg):
    plan = bad_plan(runtime_cfg)
    plan.add("z", "TopK", ["r"], n=3)
    assert any(e.startswith("1:") for e in plan.validate())


def test_rule2_missing_input(runtime_cfg):
    plan = bad_plan(runtime_cfg)
    plan.nodes["f"].inputs.append("zz")
    assert any(e.startswith("2:") for e in plan.validate())


def test_rule2_cycle(runtime_cfg):
    plan = bad_plan(runtime_cfg)
    plan.nodes["s0"].inputs.append("r")
    plan.nodes["s0"].op = "Mask"
    assert any(e.startswith("2:") or e.startswith("3:") for e in plan.validate())


def test_rule3_wrong_input_type(runtime_cfg):
    plan = bad_plan(runtime_cfg)
    plan.nodes["r"].inputs = ["s0"]
    assert any(e.startswith("3:") for e in plan.validate())


def test_rule4_soft_predicate_in_filter(runtime_cfg):
    plan = bad_plan(runtime_cfg)
    plan.nodes["b2"].args["preds"] = [C("year", ">=", 2000, "soft")]
    assert any(e.startswith("4:") for e in plan.validate())


def test_rule5_fuse_needs_ranked_lists(runtime_cfg):
    plan = bad_plan(runtime_cfg)
    plan.nodes["f"].inputs = ["a2", "s0"]
    assert any(e.startswith("5:") for e in plan.validate())


def test_rule6_c_n_without_filter(runtime_cfg):
    plan = bad_plan(runtime_cfg)
    plan.nodes["f"].inputs = ["a1", "b2"]
    del plan.nodes["a2"]
    assert any(e.startswith("6:") for e in plan.validate())


@pytest.mark.parametrize("op", ["Unknown"])
def test_unknown_operator(runtime_cfg, op):
    plan = bad_plan(runtime_cfg)
    plan.nodes["r"].op = op
    assert any("unknown operator" in e for e in plan.validate())
