"""Spec: Recommendation Engine Specification §2 (11.2), §7; SRS FR-13."""

from __future__ import annotations

import random

import faiss
import numpy as np
import pytest

from cineverse.runtime.semantic_index import (
    FaissFlatIndex,
    IndexUnavailable,
    NumpyIndex,
    open_index,
)
from tests.stub_encoder import StubEncoder

N = 300


def build_faiss(emb: np.ndarray, ids: np.ndarray) -> faiss.IndexIDMap:
    index = faiss.IndexIDMap(faiss.IndexFlatIP(emb.shape[1]))
    index.add_with_ids(emb, ids)
    return index


@pytest.fixture(scope="module")
def corpus():
    enc = StubEncoder()
    ids = np.arange(1, N + 1, dtype=np.int64) * 7  # non-contiguous ids
    texts = [f"movie {i}" for i in range(N)]
    emb = enc.encode(texts)
    return enc, ids, emb


@pytest.fixture(scope="module")
def backends(corpus):
    enc, ids, emb = corpus
    return NumpyIndex(emb, ids, enc), FaissFlatIndex(build_faiss(emb, ids), emb, ids, enc)


def test_both_backends_are_exact(backends):
    assert all(b.exact for b in backends)


def test_faiss_equals_numpy_on_50_queries_full_and_scoped(backends, corpus):
    """Engine Spec §7: FAISS == NumPy, full and scoped."""
    numpy_idx, faiss_idx = backends
    _, ids, _ = corpus
    rng = random.Random(42)
    for q in range(50):
        text = f"query {q}"
        scope = np.array(sorted(rng.sample(ids.tolist(), rng.randint(1, N))), dtype=np.int64)
        for sc in (None, scope):
            a, b = numpy_idx.search(text, sc, 40), faiss_idx.search(text, sc, 40)
            assert a.ids == b.ids
            assert np.allclose(a.scores, b.scores, atol=1e-6)


def test_scoped_search_returns_only_scope(backends, corpus):
    _, ids, _ = corpus
    scope = ids[:10]
    for idx in backends:
        assert set(idx.search("x", scope, 200).ids) <= set(scope.tolist())
        assert len(idx.search("x", scope, 200)) == 10


def test_scoped_search_equals_filtered_full_search(backends, corpus):
    """The O4 argument: exact scoped search = full search filtered to the scope."""
    _, ids, _ = corpus
    scope = ids[::3]
    allowed = set(scope.tolist())
    for idx in backends:
        full = [m for m in idx.search("pushdown", None, N).ids if m in allowed][:25]
        assert list(idx.search("pushdown", scope, 25).ids) == full


def test_empty_text_returns_empty_list_without_encoder_call(corpus):
    enc, ids, emb = corpus
    idx = NumpyIndex(emb, ids, enc)
    before = enc.calls
    assert len(idx.search("", None, 10)) == 0
    assert enc.calls == before


def test_self_retrieval(backends, corpus):
    _, ids, _ = corpus
    for idx in backends:
        rl = idx.search("movie 17", None, 1)
        assert rl.ids == (int(ids[17]),) and rl.scores[0] == pytest.approx(1.0, abs=1e-5)


def test_evidence_has_rank_and_score(backends):
    rl = backends[0].search("q", None, 3)
    assert [rl.evidence[m]["semantic_rank"] for m in rl.ids] == [1, 2, 3]
    assert rl.evidence[rl.ids[0]]["semantic_score"] == rl.scores[0]


def test_missing_artifacts_raise_index_unavailable(tmp_path):
    with pytest.raises(IndexUnavailable):
        open_index("numpy", tmp_path, StubEncoder())
