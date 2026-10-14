"""Spec: Compiler Front-End Specification §6, §9 (each rule: ≥ 2 positive, 1 negative)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cineverse.compiler.lexer import lex
from cineverse.compiler.parser import parse
from cineverse.compiler.semantic import analyse

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = json.loads(
    (ROOT / "docs" / "CineVerse_Example_Requests_and_Expected_Outputs.json").read_text("utf-8")
)["examples"]


@pytest.fixture
def sem(registry):
    def run(text: str):
        return analyse(parse(lex(text, registry)[0], text)[0], registry)

    return run


@pytest.fixture
def codes(sem):
    return lambda text: [d.code for d in sem(text).diagnostics]


@pytest.fixture
def anns(sem):
    def run(text: str):
        return [(a.kind, a.field, a.op, a.value, a.polarity, a.strictness)
                for v in sem(text).annotations.values() for a in v if a.applied]

    return run


@pytest.mark.parametrize("ex", EXAMPLES, ids=[e["id"] for e in EXAMPLES])
def test_example_diagnostic_codes(ex, registry):
    """Invalid and warning examples produce exactly their codes (with lexer/parser codes)."""
    tokens, lex_d = lex(ex["text"], registry)
    ast, parse_d = parse(tokens, ex["text"])
    got = [d.code for d in lex_d + parse_d + analyse(ast, registry).diagnostics]
    assert got == ex["expected"]["diagnostics"]


# S1 ------------------------------------------------------------------------------------------
def test_s1_alias_resolves_to_canonical(anns):
    assert ("pref", "genre", None, "Sci-Fi", 1, "soft") in anns("scifi")


def test_s1_near_genre_typo_gets_s101_with_hint(sem):
    (d,) = sem("comdey").diagnostics
    assert (d.code, d.severity.value, d.hint) == ("S101", "INFO", "Did you mean Comedy?")


def test_s1_ordinary_unknown_word_no_s101(codes):
    assert codes("kubrick style") == []


# S2 ------------------------------------------------------------------------------------------
def test_s2_unit_infers_field(anns):
    assert ("constraint", "votes", ">=", 50, None, "hard") in anns("comedy at least 50 votes")


def test_s2_year_value_infers_year(anns):
    assert ("constraint", "year", "<", 1990, None, "hard") in anns("drama before 1990")


def test_s2_uninferable_gives_s102(codes):
    assert codes("comedy above 7") == ["S102"]


# S3 ------------------------------------------------------------------------------------------
def test_s3_fractional_year_rejected(codes):
    assert codes("released after 2010.5") == ["S103"]


def test_s3_fractional_votes_rejected(codes):
    assert codes("at least 3.5 votes") == ["S103"]


def test_s3_integer_rating_is_accepted_as_float(anns):
    assert ("constraint", "rating", ">=", 4.0, None, "hard") in anns("rated at least 4")


# S4 ------------------------------------------------------------------------------------------
def test_s4_rating_out_of_range(sem):
    (d,) = sem("rated above 9").diagnostics
    assert d.message == "9 is outside the range of rating (0.5–5.0)"


def test_s4_limit_clamped_with_s109(sem):
    s = sem("top 100 action")
    assert [d.message for d in s.diagnostics] == ["Number of results limited to 50"]
    assert [a.value for v in s.annotations.values() for a in v if a.kind == "limit"] == [50]


def test_s4_missing_limit_number_uses_default(sem):
    s = sem("show me comedies")
    assert [a.value for v in s.annotations.values() for a in v if a.kind == "limit"] == [10]


def test_s4_in_range_no_diagnostic(codes):
    assert codes("rated at least 4.5 stars") == []


# S5 ------------------------------------------------------------------------------------------
def test_s5_hours_converted_to_minutes(sem):
    d = sem("comedy under 2 hours").diagnostics[0]
    assert (d.code, d.message) == ("S112", "Converted 2 hours to 120 minutes")


def test_s5_minutes_not_converted(codes):
    assert "S112" not in codes("comedy under 90 minutes")


def test_s5_converted_value_stored(sem):
    s = sem("drama under 2 hours")
    values = [a.value for v in s.annotations.values() for a in v if a.field == "runtime"]
    assert values == [120]


# S6 ------------------------------------------------------------------------------------------
def test_s6_runtime_unavailable_not_applied(sem, anns):
    assert [d.code for d in sem("drama under 90 minutes").diagnostics] == ["S105"]
    assert not any(a[1] == "runtime" for a in anns("drama under 90 minutes"))


def test_s6_diversity_unavailable(codes):
    assert codes("diverse comedies") == ["S105"]


def test_s6_available_field_applied(anns):
    assert any(a[1] == "year" for a in anns("comedy after 2000"))


# S7 ------------------------------------------------------------------------------------------
def test_s7_strict_genre_is_hard_has(anns):
    assert anns("only westerns") == [("constraint", "genre", "HAS", "Western", None, "hard")]


def test_s7_hard_exclusion_of_genre(anns):
    assert anns("no horror") == [("constraint", "genre", "NOT_HAS", "Horror", None, "hard")]


def test_s7_soft_and_hedged_exclusions(anns):
    assert anns("little romance")[0][4:] == (-1, "soft")
    assert anns("ideally no horror")[0][4:] == (-1, "soft")


def test_s7_hedged_constraint_soft(anns):
    assert anns("preferably after 2000")[0][5] == "soft"


def test_s7_between_and_decade_give_two_bounds(anns):
    assert [a[2:4] for a in anns("between 2000 and 2010")] == [(">=", 2000), ("<=", 2010)]
    assert [a[2:4] for a in anns("90s")] == [(">=", 1990), ("<=", 1999)]


def test_s7_strict_descriptor_soft_with_s106(sem):
    s = sem("only dark")
    assert [d.code for d in s.diagnostics] == ["S106"]


# S8 ------------------------------------------------------------------------------------------
def test_s8_descriptor_exclusion_softened(sem, anns):
    assert [d.message for d in sem("no gore").diagnostics] == [
        "'gore' cannot be checked exactly; applied as a preference"]
    assert anns("no gore") == [("pref", "text", None, "gore", -1, "soft")]


def test_s8_soft_descriptor_exclusion_no_warning(codes):
    assert codes("not too violent") == []


def test_s8_hedged_descriptor_exclusion_no_warning(codes):
    assert codes("ideally no gore") == []


# S9 ------------------------------------------------------------------------------------------
def test_s9_contradiction(sem):
    (d,) = sem("only horror and no horror").diagnostics
    assert (d.code, d.span, d.message) == ("S107", (0, 25), "Horror is both required and excluded")


def test_s9_alias_contradiction(codes):
    assert codes("only scary movies, no horror") == ["S107"]


def test_s9_soft_opposite_is_not_contradiction(codes):
    assert "S107" not in codes("only horror, little horror")


# S10 -----------------------------------------------------------------------------------------
def test_s10_empty_year_range(codes):
    assert codes("after 2015 before 2000") == ["S108"]


def test_s10_int_strict_bounds_meeting(codes):
    assert codes("after 2000 before 2001") == ["S108"]


def test_s10_touching_closed_bounds_ok(codes):
    assert codes("from 2000 up to 2000") == []


# S11 -----------------------------------------------------------------------------------------
def test_s11_soft_positive_overridden_by_hard_exclusion(sem, anns):
    assert [d.code for d in sem("comedy, no comedy").diagnostics] == ["S110"]
    assert anns("comedy, no comedy") == [("constraint", "genre", "NOT_HAS", "Comedy", None, "hard")]


def test_s11_soft_negative_overridden_by_hard_has(codes):
    assert codes("only horror, little horror") == ["S110"]


def test_s11_unrelated_genres_untouched(codes):
    assert codes("comedy, no horror") == []


# S12 -----------------------------------------------------------------------------------------
def test_s12_nothing_to_recommend(codes):
    assert codes("something please") == ["S111"]


def test_s12_only_unapplied_conditions(codes):
    assert codes("under 2 hours") == ["S112", "S105", "S111"]


def test_s12_limit_alone_is_not_enough_but_genre_is(codes):
    assert codes("top 5") == ["S111"]
    assert codes("top 5 comedies") == []


# S13 -----------------------------------------------------------------------------------------
def test_s13_strict_or_becomes_soft(sem, anns):
    assert [d.code for d in sem("only comedy or drama").diagnostics] == ["S114"]
    assert {a[3] for a in anns("only comedy or drama")} == {"Comedy", "Drama"}
    assert all(a[5] == "soft" for a in anns("only comedy or drama"))


def test_s13_strict_without_or_one_hard_has_per_genre(anns):
    assert [a[2:4] for a in anns("only animated comedies")] == [("HAS", "Animation"),
                                                                ("HAS", "Comedy")]


def test_s13_plain_or_no_warning(codes):
    assert codes("comedy or drama") == []


# Ordering and purity --------------------------------------------------------------------------
def test_diagnostics_ordered_by_rule_then_span(codes):
    assert codes("comedy under 2 hours, top 99") == ["S109", "S112", "S105"]


def test_analyse_is_pure(sem):
    a, b = sem("dark sci-fi after 2010, no romance"), sem("dark sci-fi after 2010, no romance")
    assert a.annotations == b.annotations and a.diagnostics == b.diagnostics
