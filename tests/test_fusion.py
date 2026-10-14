"""Spec: Recommendation Engine Specification §2 (11.4), §3."""

from __future__ import annotations

import pytest

from cineverse.runtime.context import RankedList
from cineverse.runtime.fusion import rank_key, rrf, z_for


def ranked(ids: list[int], source: str = "semantic") -> RankedList:
    return RankedList(tuple(ids), tuple(1.0 / (i + 1) for i in range(len(ids))), source, {})


def test_z_is_constant_two_over_k_plus_one():
    assert z_for(60) == pytest.approx(2 / 61)


def test_hand_computed_example_rank_2_and_rank_5():
    """Engine Spec §3: RRF/Z = 0.961166."""
    sem = ranked([100, 7, 101, 102, 103])
    meta = ranked([200, 201, 202, 203, 7], "metadata")
    out = rrf([sem, meta], 60, z_for(60))
    i = out.ids.index(7)
    assert round(out.scores[i], 6) == 0.961166


def test_single_list_rank_one_scores_one_half():
    out = rrf([ranked([5])], 60, z_for(60))
    assert out.scores == (pytest.approx(0.5),)


def test_empty_list_contributes_nothing():
    """O3 relies on this: removing an empty source leaves scores unchanged."""
    a = rrf([ranked([1, 2, 3])], 60, z_for(60))
    b = rrf([ranked([1, 2, 3]), RankedList.empty("semantic")], 60, z_for(60))
    assert a.ids == b.ids and a.scores == b.scores


def test_ties_broken_by_movie_id():
    out = rrf([ranked([9]), ranked([3], "metadata")], 60, z_for(60))
    assert out.ids == (3, 9)


def test_rank_key_rounds_to_six_decimals():
    assert rank_key(0.1234564, 5) == rank_key(0.1234561, 5)
    assert sorted([(0.5000001, 9), (0.5000002, 3)], key=lambda s: rank_key(*s))[0][1] == 3


def test_evidence_is_merged_across_lists():
    sem = RankedList((1,), (1.0,), "semantic", {1: {"semantic_rank": 1}})
    meta = RankedList((1,), (2.0,), "metadata", {1: {"metadata_rank": 1}})
    ev = rrf([sem, meta], 60, z_for(60)).evidence[1]
    assert ev["semantic_rank"] == 1 and ev["metadata_rank"] == 1 and "rrf" in ev
