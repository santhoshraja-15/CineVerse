"""Spec: Recommendation Engine Specification §2 (11.5), §3."""

from __future__ import annotations

import pytest

from cineverse.compiler.ir import Constraint, Preference
from cineverse.runtime.context import RankedList
from cineverse.runtime.scoring import soft_score, tag_match


def P(kind: str, value: str, polarity: int) -> Preference:
    return Preference(kind=kind, value=value, polarity=polarity)


def test_hand_computed_score_0_861166(toy_catalog, soft_cfg):
    """Engine Spec §3: 0.961166 + 2×0.10 − 1×0.30 = 0.861166 (movie 5: Sci-Fi, Romance)."""
    rl = RankedList((5,), (0.961166,), "rrf", {})
    prefs = [P("genre", "Sci-Fi", 1), P("text", "thoughtful", 1), P("genre", "Romance", -1)]
    out = soft_score(toy_catalog, rl, prefs, [], soft_cfg)
    assert round(out.scores[0], 6) == 0.861166


def test_unknown_soft_value_counts_as_violation(toy_catalog, soft_cfg):
    soft = [Constraint(field="year", op=">=", value=2001, strictness="soft", span=(0, 0))]
    rl = RankedList((7, 1), (0.5, 0.5), "rrf", {})
    out = soft_score(toy_catalog, rl, [], soft, soft_cfg)
    scores = dict(zip(out.ids, out.scores, strict=True))
    assert scores[7] == pytest.approx(0.3)  # unknown year
    assert scores[1] == pytest.approx(0.5)  # 2012 satisfies


def test_soft_scoring_reranks_and_breaks_ties_by_id(toy_catalog, soft_cfg):
    rl = RankedList((3, 1, 8), (0.6, 0.55, 0.5), "rrf", {})
    out = soft_score(toy_catalog, rl, [P("genre", "Romance", -1)], [], soft_cfg)
    assert out.ids == (1, 8, 3)


def test_sums_not_fractions_two_matches_add_twice(toy_catalog, soft_cfg):
    rl = RankedList((1,), (0.0,), "rrf", {})
    out = soft_score(toy_catalog, rl, [P("genre", "Sci-Fi", 1), P("genre", "Mystery", 1)],
                     [], soft_cfg)
    assert out.scores[0] == pytest.approx(0.2)


def test_evidence_records_matches_and_violations(toy_catalog, soft_cfg):
    soft = [Constraint(field="year", op=">=", value=2013, strictness="soft", span=(1, 2))]
    rl = RankedList((5,), (0.4,), "rrf", {5: {"semantic_rank": 3}})
    ev = soft_score(toy_catalog, rl, [P("text", "time travel", 1)], soft, soft_cfg).evidence[5]
    assert ev["semantic_rank"] == 3
    assert ev["soft"]["pos_matches"] == [["text", "time travel", "time travel"]]
    assert ev["soft"]["violated"] == []


def test_tag_match_is_whole_word_or_phrase():
    assert tag_match("dark", ["dark comedy"]) == "dark comedy"
    assert tag_match("thought", ["thought-provoking"]) == "thought-provoking"
    assert tag_match("thoughtful", ["thought-provoking"]) is None
    assert tag_match("art", ["dark"]) is None
