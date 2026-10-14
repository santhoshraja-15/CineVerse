"""Spec: Recommendation Engine Specification §2 (11.5); SRS FR-05.2, FR-16."""

from __future__ import annotations

import random

import numpy as np
import pytest

from cineverse.compiler.ir import Constraint
from cineverse.runtime.constraints import filter_list, mask
from cineverse.runtime.context import RankedList


def C(field: str, op: str, value, strictness: str = "hard") -> Constraint:
    return Constraint(field=field, op=op, value=value, strictness=strictness, span=(0, 0))


def all_ids(cat) -> np.ndarray:
    return cat.all_ids()


@pytest.mark.parametrize(
    ("pred", "expected"),
    [
        (C("genre", "HAS", "Comedy"), [3, 8, 11]),
        (C("genre", "NOT_HAS", "Sci-Fi"), [2, 3, 4, 6, 7, 8, 9, 11, 12]),
        (C("year", ">=", 2015), [3, 10, 12]),
        (C("year", "<=", 1965), [6]),
        (C("year", ">", 2015), [10, 12]),
        (C("year", "<", 1994), [6]),
        (C("rating", ">=", 4.0), [1, 5, 11]),
        (C("votes", "<=", 15), [6, 7, 12]),
    ],
)
def test_each_operator(toy_catalog, pred, expected):
    assert mask(toy_catalog, all_ids(toy_catalog), [pred]).tolist() == expected


def test_unknown_value_never_satisfies(toy_catalog):
    """Movie 7 has no year and no rating: it fails both directions."""
    ids = all_ids(toy_catalog)
    for pred in (C("year", ">=", 0), C("year", "<=", 3000), C("rating", ">=", 0.0)):
        assert 7 not in mask(toy_catalog, ids, [pred]).tolist()


def test_unavailable_field_never_satisfies(toy_catalog):
    assert mask(toy_catalog, all_ids(toy_catalog), [C("runtime", "<=", 120)]).size == 0


def test_mask_keeps_scope_order_and_respects_scope(toy_catalog):
    scope = np.array([12, 3, 8], dtype=np.int64)
    assert mask(toy_catalog, scope, [C("year", ">=", 1990)]).tolist() == [12, 3, 8]


def test_filter_list_keeps_order_renumbers_and_truncates(toy_catalog):
    rl = RankedList(
        (10, 3, 12, 1), (0.9, 0.8, 0.7, 0.6), "semantic",
        {m: {"semantic_rank": r} for r, m in enumerate((10, 3, 12, 1), 1)},
    )
    out = filter_list(toy_catalog, rl, [C("year", ">=", 2015)], c=2)
    assert out.ids == (10, 3)
    assert out.scores == (0.9, 0.8)
    assert out.evidence[3]["semantic_rank"] == 2


def test_filter_list_empty_preds_only_truncates(toy_catalog):
    rl = RankedList((1, 2, 3), (3.0, 2.0, 1.0), "metadata", {})
    assert filter_list(toy_catalog, rl, [], c=2).ids == (1, 2)


def test_mask_equals_filter_list_on_random_lists(toy_catalog):
    """Engine Spec §7: mask == filter_list."""
    rng = random.Random(42)
    ids = all_ids(toy_catalog).tolist()
    preds_pool = [C("year", ">=", 2000), C("genre", "NOT_HAS", "Comedy"),
                  C("rating", ">=", 3.5), C("votes", ">=", 40), C("genre", "HAS", "Sci-Fi")]
    for _ in range(50):
        order = rng.sample(ids, len(ids))
        preds = rng.sample(preds_pool, rng.randint(0, 3))
        rl = RankedList(tuple(order), tuple(range(len(order), 0, -1)), "semantic", {})
        via_filter = filter_list(toy_catalog, rl, preds, c=len(order)).ids
        allowed = set(mask(toy_catalog, np.array(order), preds).tolist())
        assert via_filter == tuple(m for m in order if m in allowed)
