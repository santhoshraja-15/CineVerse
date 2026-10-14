"""Spec: Recommendation Engine Specification §2 (11.3), §7."""

from __future__ import annotations

import numpy as np

from cineverse.runtime.metadata_search import popularity, search


def test_sort_key_genres_then_tags_then_bayes_then_id(toy_catalog):
    out = search(toy_catalog, ["Sci-Fi", "Mystery"], ["space"], toy_catalog.all_ids(), 200)
    # 1: 2 genres + space; 5: 1 genre; 9: 1 genre; 10: 1 genre + space
    assert out.ids[:2] == (1, 10)
    assert out.ids[2:] == (5, 9)  # equal matches: higher bayes first (3.90 > 3.82)


def test_score_is_genres_plus_half_tags(toy_catalog):
    out = search(toy_catalog, ["Sci-Fi"], ["space"], toy_catalog.all_ids(), 200)
    assert out.scores[0] == 1.5


def test_tag_phrase_matching(toy_catalog):
    out = search(toy_catalog, [], ["twist ending"], toy_catalog.all_ids(), 200)
    assert set(out.ids) == {2, 9}
    assert out.evidence[2]["matched_tags"] == [["twist ending", "twist ending"]]


def test_movies_without_a_match_are_excluded(toy_catalog):
    out = search(toy_catalog, ["Western"], [], toy_catalog.all_ids(), 200)
    assert out.ids == (6,)


def test_no_genres_and_no_terms_gives_empty_list(toy_catalog):
    assert len(search(toy_catalog, [], [], toy_catalog.all_ids(), 200)) == 0


def test_scope_and_truncation_respected(toy_catalog):
    out = search(toy_catalog, ["Comedy"], [], np.array([3, 8], dtype=np.int64), 1)
    assert out.ids == (8,)
    assert out.evidence[8]["metadata_rank"] == 1


def test_popularity_orders_by_bayes_then_id(toy_catalog):
    out = popularity(toy_catalog, toy_catalog.all_ids(), 3)
    assert out.ids == (1, 11, 5)
    assert out.evidence[1] == {"popularity_rank": 1, "bayes": out.scores[0], "rating":
                               out.evidence[1]["rating"], "votes": 120}


def test_popularity_ties_broken_by_id(toy_catalog):
    out = popularity(toy_catalog, np.array([12, 7], dtype=np.int64), 2)
    # bayes 3.52 (id 12) > 3.50 (id 7)
    assert out.ids == (12, 7)
