"""Spec: Compiler Front-End Specification §4, §5, §9; SRS FR-03, FR-03.1."""

from __future__ import annotations

import pytest

from cineverse.compiler.ast import (
    ConstraintClause,
    DescriptorTerm,
    DiversityClause,
    ErrorNode,
    ExclusionClause,
    GenreTerm,
    LimitClause,
    PreferenceClause,
    to_dict,
    walk,
)
from cineverse.compiler.lexer import lex
from cineverse.compiler.parser import parse


@pytest.fixture
def p(registry):
    def run(text: str):
        tokens, _ = lex(text, registry)
        return parse(tokens, text)

    return run


def kinds(ast) -> list[str]:
    return [type(c).__name__ for c in ast.clauses]


# --------------------------------------------------------------------------- productions


def test_preference_terms_and_trailing_item(p):
    ast, diags = p("dark sci-fi movies")
    (c,) = ast.clauses
    assert isinstance(c, PreferenceClause) and c.modifier == "NONE" and not c.has_or
    assert isinstance(c.terms[0], DescriptorTerm) and isinstance(c.terms[1], GenreTerm)
    assert c.span == (0, 18) and diags == []


def test_strict_preference(p):
    (c,) = p("only animated comedies")[0].clauses
    assert c.modifier == "STRICT" and [t.genres for t in c.terms] == [("Animation",), ("Comedy",)]


def test_hedged_preference(p):
    (c,) = p("maybe a western")[0].clauses
    assert isinstance(c, PreferenceClause) and c.modifier == "HEDGE"


def test_or_in_preference_sets_has_or(p):
    (c,) = p("only comedy or drama")[0].clauses
    assert c.has_or and len(c.terms) == 2


def test_exclusion_hard_and_soft(p):
    ast, _ = p("no horror, little romance")
    assert [(c.strength, c.hedged) for c in ast.clauses] == [("HARD", False), ("SOFT", False)]


def test_or_in_exclusion(p):
    (c,) = p("without horror or gore")[0].clauses
    assert isinstance(c, ExclusionClause) and len(c.targets) == 2


def test_exclusion_target_list_continues_only_through_or(p):
    """'no horror comedy' = exclusion(Horror) + preference(Comedy)."""
    ast, _ = p("no horror comedy")
    assert kinds(ast) == ["ExclusionClause", "PreferenceClause"]


def test_constraint_cmp_number(p):
    (c,) = p("after 2010")[0].clauses
    assert isinstance(c, ConstraintClause) and (c.op, c.values[0].value) == (">", 2010)
    assert c.field_raw is None


def test_constraint_with_field_and_unit_on_quantity(p):
    (c,) = p("rated at least 4 stars")[0].clauses
    assert (c.field_raw, c.op, c.values[0].value, c.values[0].unit_raw) == ("rated", ">=", 4,
                                                                             "stars")


def test_constraint_between_with_and(p):
    (c,) = p("between 2000 and 2010")[0].clauses
    assert c.op == "BETWEEN" and [v.value for v in c.values] == [2000, 2010]


def test_constraint_between_with_to(p):
    (c,) = p("between 1 to 3 hours")[0].clauses
    assert c.op == "BETWEEN" and c.values[1].unit_raw == "hours"


def test_constraint_decade(p):
    (c,) = p("90s")[0].clauses
    assert c.op == "DECADE" and [v.value for v in c.values] == [1990, 1999]


def test_limit_forms(p):
    assert [c.n for c in p("top 5")[0].clauses] == [5]
    assert [c.n for c in p("show me")[0].clauses] == [None]
    assert [c.n for c in p("give me 8 films")[0].clauses] == [8]
    assert isinstance(p("3 movies")[0].clauses[0], LimitClause)


def test_diversity(p):
    ast, _ = p("varied picks")
    assert isinstance(ast.clauses[0], DiversityClause)


# --------------------------------------------------------------------------- separators


def test_separator_optional_between_clauses(p):
    ast, _ = p("sci-fi mystery after 2010")
    assert kinds(ast) == ["PreferenceClause", "ConstraintClause"]


def test_separator_between_clauses(p):
    assert kinds(p("comedy, after 2010; top 3")[0]) == [
        "PreferenceClause", "ConstraintClause", "LimitClause"]


def test_leading_trailing_and_double_separators_are_skipped(p):
    ast, diags = p(", comedy,, ")
    assert kinds(ast) == ["PreferenceClause"] and diags == []


def test_two_constraints_without_separator(p):
    assert kinds(p("after 2015 before 2000")[0]) == ["ConstraintClause", "ConstraintClause"]


# --------------------------------------------------------------------------- LL(2) at HEDGE


def test_hedge_then_cmp_is_constraint(p):
    (c,) = p("preferably after 2000")[0].clauses
    assert isinstance(c, ConstraintClause) and c.hedged


def test_hedge_then_neg_is_exclusion(p):
    (c,) = p("ideally no horror")[0].clauses
    assert isinstance(c, ExclusionClause) and c.hedged and c.strength == "HARD"


def test_hedge_then_term_is_preference(p):
    (c,) = p("ideally horror")[0].clauses
    assert isinstance(c, PreferenceClause) and c.modifier == "HEDGE"


def test_hedge_then_field_is_constraint(p):
    (c,) = p("preferably released before 1990")[0].clauses
    assert isinstance(c, ConstraintClause) and c.field_raw == "released"


# --------------------------------------------------------------------------- recovery


def test_p001_unit_cannot_start_clause_and_drama_kept(p):
    """Frontend Spec §8: 'drama, stars'."""
    ast, diags = p("drama, stars")
    assert kinds(ast) == ["PreferenceClause", "ErrorNode"]
    assert [(d.code, d.span) for d in diags] == [("P001", (7, 12))]


def test_p001_recovery_resynchronises_at_next_clause(p):
    ast, diags = p("under stars comedy")
    assert kinds(ast) == ["ErrorNode", "PreferenceClause"]
    assert ast.clauses[0].text == "under stars" and diags[0].code == "P001"


def test_p002_stray_number_skips_only_that_token(p):
    ast, diags = p("comedies 42 thriller")
    assert kinds(ast) == ["PreferenceClause", "PreferenceClause"]
    assert [(d.code, d.message) for d in diags] == [("P002", "Number 42 has no meaning here")]


def test_between_without_second_number_recovers(p):
    ast, diags = p("between 2000 and comedy")
    assert isinstance(ast.clauses[0], ErrorNode) and diags[0].code == "P001"
    assert isinstance(ast.clauses[-1], PreferenceClause)


def test_every_request_yields_an_ast(p):
    for text in ["or or or", "to", "stars ratings", "rated", "no", "only"]:
        ast, diags = p(text)
        assert ast is not None and all(d.code in ("P001", "P002") for d in diags)


# --------------------------------------------------------------------------- AST shape


def test_empty_after_filler_has_no_clauses(p):
    ast, diags = p("something please")
    assert ast.clauses == () and diags == []


def test_node_ids_unique_and_preorder(p):
    ast, _ = p("thoughtful sci-fi mystery after 2010, little romance, top 5")
    ids = [n.node_id for n in walk(ast)]
    assert ids == sorted(ids) and len(set(ids)) == len(ids) and ids[0] == 0


def test_to_dict_is_json_ready(p):
    ast, _ = p("no musicals")
    d = to_dict(ast)
    assert d["kind"] == "RequestNode" and d["span"] == [0, 11]
    assert d["clauses"][0]["targets"][0] == {
        "kind": "GenreTerm", "raw": "musicals", "genres": ["Musical"], "span": [3, 11],
        "node_id": 2,
    }


def test_ex01_spans_match_the_report(p):
    ast, _ = p("thoughtful sci-fi mystery after 2010, little romance, top 5")
    assert [c.span for c in ast.clauses] == [(0, 25), (26, 36), (38, 52), (54, 59)]


def test_parser_is_pure(p):
    assert p("only comedies in the 90s") == p("only comedies in the 90s")
