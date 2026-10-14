"""Spec: Optimizer and Equivalence Testing Specification §3, §3.1, §8 (O2, O1)."""

from __future__ import annotations

from cineverse.compiler.ir import Channels, CompiledQuery, Constraint, Preference, validate
from cineverse.compiler.passes import run_ir_passes


def C(field, op, value, strictness="hard"):
    return Constraint(field=field, op=op, value=value, strictness=strictness, span=(0, 0))


def P(kind, value, polarity=1):
    return Preference(kind=kind, value=value, polarity=polarity)


def q(cons=(), prefs=()) -> CompiledQuery:
    return CompiledQuery(source="s", semantic_text="", preferences=list(prefs),
                         constraints=list(cons), channels=Channels(semantic=True))


def ops(ir) -> list[tuple[str, str, object, str]]:
    return [(c.field, c.op, c.value, c.strictness) for c in ir.constraints]


# --------------------------------------------------------------------------- O2


def test_o2_rewrites_int_strict_bounds():
    ir, log = run_ir_passes(q([C("year", ">", 2010), C("votes", "<", 100)]), {"O2"})
    assert ops(ir) == [("votes", "<=", 99, "hard"), ("year", ">=", 2011, "hard")]
    assert log[0].display() == "O2: year > 2010 -> year >= 2011; votes < 100 -> votes <= 99"


def test_o2_soft_rewrite_is_labelled():
    _, log = run_ir_passes(q([C("year", ">", 2000, "soft")]), {"O2"})
    assert log[0].detail == "year > 2000 -> year >= 2001 (soft)"


def test_o2_negative_rating_float_unchanged():
    ir, log = run_ir_passes(q([C("rating", ">", 4.0)]), {"O2"})
    assert ops(ir) == [("rating", ">", 4.0, "hard")] and log == []


def test_o2_sorts_and_dedupes_silently():
    ir, log = run_ir_passes(q(prefs=[P("text", "dark"), P("genre", "Mystery"), P("text", "dark")]),
                            {"O2"})
    assert [p.value for p in ir.preferences] == ["Mystery", "dark"] and log == []


def test_o2_is_idempotent():
    once, _ = run_ir_passes(q([C("year", "<", 1990), C("genre", "HAS", "Drama")]), {"O2"})
    twice, log = run_ir_passes(once, {"O2"})
    assert twice == once and log == []


def test_o2_result_satisfies_v5(registry):
    ir, _ = run_ir_passes(q([C("year", ">", 2000), C("rating", ">=", 3.0)],
                            [P("text", "z"), P("genre", "Comedy")]), {"O2"})
    assert validate(ir, registry, after_passes=True) == []


# --------------------------------------------------------------------------- O1


def test_o1_keeps_tighter_of_two_hard_bounds():
    ir, log = run_ir_passes(q([C("year", ">", 2000), C("year", ">", 2010)]), {"O2", "O1"})
    assert ops(ir) == [("year", ">=", 2011, "hard")]
    assert [r.display() for r in log] == [
        "O2: year > 2000 -> year >= 2001; year > 2010 -> year >= 2011",
        "O1: hard year >= 2001 subsumed by hard year >= 2011",
    ]


def test_o1_tighter_upper_bound():
    ir, _ = run_ir_passes(q([C("rating", "<=", 4.5), C("rating", "<=", 3.0)]), {"O1"})
    assert ops(ir) == [("rating", "<=", 3.0, "hard")]


def test_o1_strict_float_bound_beats_equal_closed_bound():
    ir, _ = run_ir_passes(q([C("rating", ">=", 4.0), C("rating", ">", 4.0)]), {"O1"})
    assert ops(ir) == [("rating", ">", 4.0, "hard")]


def test_o1_drops_soft_bound_implied_by_hard():
    ir, log = run_ir_passes(q([C("year", ">=", 2000, "soft"), C("year", ">=", 2011)]), {"O1"})
    assert ops(ir) == [("year", ">=", 2011, "hard")]
    assert log[0].detail == "soft year >= 2000 implied by hard year >= 2011"


def test_o1_negative_two_soft_bounds_not_merged():
    cons = [C("year", ">=", 2000, "soft"), C("year", ">=", 2010, "soft")]
    ir, log = run_ir_passes(q(cons), {"O1"})
    assert len(ir.constraints) == 2 and log == []


def test_o1_negative_opposite_directions_kept():
    cons = [C("year", "<=", 1990, "soft"), C("year", ">=", 2011)]
    ir, log = run_ir_passes(q(cons), {"O1"})
    assert len(ir.constraints) == 2 and log == []


def test_o1_negative_soft_not_implied_when_looser_hard():
    cons = [C("year", ">=", 2011, "soft"), C("year", ">=", 2000)]
    assert len(run_ir_passes(q(cons), {"O1"})[0].constraints) == 2


def test_o1_removes_duplicates_without_o2():
    ir, log = run_ir_passes(q([C("genre", "NOT_HAS", "Horror")] * 2), {"O1"})
    assert len(ir.constraints) == 1 and log[0].detail.startswith("removed duplicate")


def test_disabled_rules_do_nothing():
    ir = q([C("year", ">", 2010), C("year", ">", 2000)])
    assert run_ir_passes(ir, set()) == (ir, [])


def test_rule_log_records_before_and_after():
    _, log = run_ir_passes(q([C("year", ">", 2010)]), {"O2"})
    assert log[0].before["constraints"][0]["op"] == ">"
    assert log[0].after["constraints"][0]["op"] == ">="
