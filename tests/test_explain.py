"""Spec: Recommendation Engine Specification §2 (11.6), §4, §7."""

from __future__ import annotations

from cineverse.compiler.ir import Channels, CompiledQuery, Constraint, Output, Preference
from cineverse.runtime.context import RankedList
from cineverse.runtime.explain import explain


def ir(constraints=(), prefs=(), text="") -> CompiledQuery:
    return CompiledQuery(
        source="x", semantic_text=text, preferences=list(prefs), constraints=list(constraints),
        channels=Channels(semantic=True), output=Output(limit=5),
    )


def hard(field, op, value):
    return Constraint(field=field, op=op, value=value, strictness="hard", span=(0, 0))


def test_no_evidence_no_reasons(toy_catalog):
    rec = explain(toy_catalog, RankedList((1,), (0.5,), "topk", {1: {}}), ir())[0]
    assert rec.reasons == ()


def test_reasons_follow_template_order(toy_catalog):
    ev = {
        "semantic_rank": 2,
        "metadata_rank": 1,
        "matched_genres": ["Sci-Fi"],
        "matched_tags": [["space", "space"]],
    }
    q = ir([hard("year", ">=", 2011)], text="space science fiction")
    rec = explain(toy_catalog, RankedList((1,), (0.9,), "topk", {1: ev}), q)[0]
    assert rec.reasons == (
        "Genres Sci-Fi match your request",
        "Tagged 'space', matching 'space'",
        "Close in meaning to 'space science fiction' (rank 2)",
        "Matches your genres and keywords (rank 1)",
    )


def test_at_most_four_reasons_and_trace_keeps_all_evidence(toy_catalog):
    ev = {"semantic_rank": 1, "metadata_rank": 1, "matched_genres": ["Sci-Fi", "Mystery"],
          "matched_tags": [["space", "space"], ["thought", "thought-provoking"]]}
    rec = explain(toy_catalog, RankedList((1,), (1.0,), "topk", {1: ev}), ir(text="t"))[0]
    assert len(rec.reasons) == 4
    assert rec.evidence == ev


def test_hard_bounds_use_actual_values(toy_catalog):
    q = ir([hard("year", ">=", 2000), hard("year", "<=", 2010), hard("rating", ">=", 3.5),
            hard("genre", "NOT_HAS", "Romance")])
    rec = explain(toy_catalog, RankedList((2,), (1.0,), "topk", {2: {}}), q)[0]
    assert rec.reasons == ("Released 2005 (2000–2010)", "Rated 3.9★ (at least 3.5)",
                           "Not Romance")


def test_soft_penalty_and_violation_reasons(toy_catalog):
    soft = {"pos_matches": [], "neg_matches": [["genre", "Romance", "Romance"]],
            "violated": [{"field": "year", "op": ">=", "value": 2016, "strictness": "soft"}]}
    q = ir(prefs=[Preference(kind="genre", value="Romance", polarity=-1)])
    rec = explain(toy_catalog, RankedList((3,), (0.1,), "topk", {3: {"soft": soft}}), q)[0]
    assert rec.reasons == ("Includes Romance, which you wanted little of",
                           "Released 2015, earlier than you preferred")


def test_popularity_reason(toy_catalog):
    ev = {"popularity_rank": 1, "bayes": 4.05, "rating": 4.2, "votes": 120}
    rec = explain(toy_catalog, RankedList((1,), (0.5,), "topk", {1: ev}), ir())[0]
    assert rec.reasons == ("Highly rated: 4.2★ from 120 ratings",)
