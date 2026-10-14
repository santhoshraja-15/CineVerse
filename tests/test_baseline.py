"""Spec: Recommendation Engine Specification §5, §7; SRS FR-19."""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from cineverse.baseline.baseline import BaselineSpec, ranked_baseline, recommend_baseline
from cineverse.baseline.popularity import recommend_popularity
from cineverse.compiler.ir import Capabilities, Constraint, Preference
from cineverse.runtime.context import RuntimeContext
from cineverse.runtime.semantic_index import NumpyIndex
from tests.stub_encoder import StubEncoder


@pytest.fixture
def ctx(toy_catalog, runtime_cfg) -> RuntimeContext:
    enc = StubEncoder()
    texts = [str(t) for t in toy_catalog.column("embed_text")]
    index = NumpyIndex(enc.encode(texts), toy_catalog.all_ids(), enc)
    caps = Capabilities(exact_search=True, semantic_available=True)
    return RuntimeContext(toy_catalog, index, enc, runtime_cfg, caps)


def hard(field, op, value):
    return Constraint(field=field, op=op, value=value, strictness="hard", span=(0, 0))


def soft(field, op, value):
    return Constraint(field=field, op=op, value=value, strictness="soft", span=(0, 0))


def spec(**kw) -> BaselineSpec:
    base = dict(semantic_text="", pos_genres=[], pos_terms=[], neg_soft=[], hard=[],
                soft_constraints=[], limit=5)
    base.update(kw)
    return BaselineSpec(**base)


HAND_SPECS = [
    spec(semantic_text="science fiction mystery", pos_genres=["Mystery", "Sci-Fi"]),
    spec(pos_genres=["Comedy"], hard=[hard("genre", "NOT_HAS", "Romance")]),
    spec(hard=[hard("genre", "NOT_HAS", "Romance")]),
    spec(pos_terms=["twist ending"], semantic_text="twist ending"),
    spec(pos_genres=["Sci-Fi"], semantic_text="science fiction",
         neg_soft=[Preference(kind="genre", value="Romance", polarity=-1)]),
    spec(pos_genres=["Drama"], semantic_text="drama", soft_constraints=[soft("year", ">=", 2010)]),
    spec(hard=[hard("year", ">=", 2010), hard("rating", ">=", 3.5)]),
    spec(pos_genres=["Comedy"], semantic_text="comedy", hard=[hard("genre", "HAS", "Comedy")]),
    spec(pos_terms=["space"], semantic_text="space", limit=2),
    spec(pos_genres=["Western"], semantic_text="western", hard=[hard("year", ">=", 2020)]),
]


@pytest.mark.parametrize("s", HAND_SPECS, ids=[f"spec{i}" for i in range(len(HAND_SPECS))])
def test_baseline_answers_hand_specs_and_honours_hard_constraints(ctx, s):
    recs = recommend_baseline(s, ctx)
    assert len(recs) <= s.limit
    for r in recs:
        for c in s.hard:
            rec = ctx.catalog.get(r.movie_id)
            if c.field == "genre":
                assert (c.value in rec.genres) == (c.op == "HAS")
            elif c.field == "year":
                assert rec.year is not None and rec.year >= c.value
            elif c.field == "rating":
                assert rec.rating is not None and rec.rating >= c.value


def test_no_positives_uses_popularity_order(ctx):
    recs = recommend_baseline(HAND_SPECS[2], ctx)
    assert [r.movie_id for r in recs] == [1, 11, 9, 2, 8]


def test_impossible_hard_constraint_returns_empty(ctx):
    assert recommend_baseline(HAND_SPECS[9], ctx) == []


def test_soft_negative_sinks_but_does_not_remove(ctx):
    plain = ranked_baseline(spec(pos_genres=["Sci-Fi"], semantic_text="science fiction",
                                 limit=12), ctx)
    sunk = ranked_baseline(dataclasses.replace(HAND_SPECS[4], limit=12), ctx)
    assert 5 in sunk.ids  # Romance movie still present
    assert sunk.ids.index(5) >= plain.ids.index(5)


def test_deterministic(ctx):
    a = recommend_baseline(HAND_SPECS[0], ctx)
    b = recommend_baseline(HAND_SPECS[0], ctx)
    assert [(r.movie_id, r.score) for r in a] == [(r.movie_id, r.score) for r in b]


def test_works_without_semantic_index(ctx):
    no_sem = RuntimeContext(ctx.catalog, None, None, ctx.cfg,
                            Capabilities(exact_search=True, semantic_available=False))
    recs = recommend_baseline(HAND_SPECS[0], no_sem)
    assert recs and all(np.isfinite(r.score) for r in recs)


def test_popularity_b0_respects_hard_constraints(ctx):
    recs = recommend_popularity([hard("year", ">=", 2010)], 3, ctx)
    assert [r.movie_id for r in recs] == [1, 5, 9]
