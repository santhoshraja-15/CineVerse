"""Exact semantic search with two interchangeable backends: FAISS flat and NumPy.

Confirmed against the installed faiss 1.15: IndexIDMap(IndexFlatIP(d)), search(x, k, params=
SearchParameters(sel=IDSelectorBatch(ids))) returns -1 ids when fewer than k exist.
Spec: CineVerse_Recommendation_Engine_Specification §2 (11.2), §2.1.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np

from cineverse.runtime.context import RankedList
from cineverse.runtime.fusion import ROUND

# FAISS ranks by raw score; extra candidates let the final (-round(score, 6), id) order decide
# ties at the cut-off exactly as the NumPy backend does.
TIE_MARGIN = 64


class IndexUnavailable(RuntimeError):
    """Index artifacts are missing or unreadable."""


class TextEncoder(Protocol):
    def encode(self, texts: list[str]) -> np.ndarray: ...


class SemanticIndex(Protocol):
    exact: bool

    def search(self, text: str, scope: np.ndarray | None, c: int) -> RankedList: ...


def _ranked(ids: np.ndarray, scores: np.ndarray, c: int) -> RankedList:
    order = np.lexsort((ids, -np.round(scores.astype(np.float64), ROUND)))[:c]
    out_ids = tuple(int(i) for i in ids[order])
    out_scores = tuple(float(s) for s in scores[order])
    evidence = {
        mid: {"semantic_rank": r, "semantic_score": s}
        for r, (mid, s) in enumerate(zip(out_ids, out_scores, strict=True), start=1)
    }
    return RankedList(out_ids, out_scores, "semantic", evidence)


class _Base:
    exact = True

    def __init__(self, embeddings: np.ndarray, ids: np.ndarray, encoder: TextEncoder) -> None:
        if embeddings.shape[0] != ids.shape[0]:
            raise IndexUnavailable("embeddings and ids have different lengths")
        self.embeddings = np.ascontiguousarray(embeddings, dtype=np.float32)
        self.ids = ids.astype(np.int64)
        self.encoder = encoder
        self._row = {int(m): i for i, m in enumerate(self.ids)}

    def _query(self, text: str) -> np.ndarray:
        return np.asarray(self.encoder.encode([text]), dtype=np.float32)[0]

    def _scope_rows(self, scope: np.ndarray | None) -> np.ndarray:
        if scope is None:
            return np.arange(len(self.ids))
        return np.fromiter(
            (self._row[int(m)] for m in scope if int(m) in self._row), dtype=np.int64
        )


class NumpyIndex(_Base):
    """Matrix product over the scope rows; exact."""

    def search(self, text: str, scope: np.ndarray | None, c: int) -> RankedList:
        if not text:
            return RankedList.empty("semantic")
        rows = self._scope_rows(scope)
        if rows.size == 0:
            return RankedList.empty("semantic")
        q = self._query(text)
        scores = self.embeddings[rows] @ q
        return _ranked(self.ids[rows], scores, c)


class FaissFlatIndex(_Base):
    """IndexIDMap(IndexFlatIP); scope via IDSelectorBatch; exact."""

    def __init__(self, index: object, embeddings: np.ndarray, ids: np.ndarray,
                 encoder: TextEncoder) -> None:
        super().__init__(embeddings, ids, encoder)
        self.index = index

    def search(self, text: str, scope: np.ndarray | None, c: int) -> RankedList:
        import faiss

        if not text:
            return RankedList.empty("semantic")
        q = self._query(text)[None, :]
        if scope is None:
            k = min(c + TIE_MARGIN, len(self.ids))
            dist, idx = self.index.search(q, k)  # type: ignore[attr-defined]
        else:
            members = np.asarray(scope, dtype=np.int64)
            members = members[np.isin(members, self.ids)]
            if members.size == 0:
                return RankedList.empty("semantic")
            k = min(c + TIE_MARGIN, members.size)
            params = faiss.SearchParameters(sel=faiss.IDSelectorBatch(members))
            dist, idx = self.index.search(q, k, params=params)  # type: ignore[attr-defined]
        keep = idx[0] >= 0
        return _ranked(idx[0][keep].astype(np.int64), dist[0][keep], c)


def open_index(backend: str, artifacts_dir: Path, encoder: TextEncoder) -> SemanticIndex:
    """Load artifacts written by `python -m cineverse.data.build_index`."""
    emb_path, ids_path = artifacts_dir / "embeddings.npy", artifacts_dir / "ids.npy"
    if not emb_path.is_file() or not ids_path.is_file():
        raise IndexUnavailable(f"missing {emb_path.name}/{ids_path.name} in {artifacts_dir}")
    embeddings, ids = np.load(emb_path), np.load(ids_path)
    if backend == "numpy":
        return NumpyIndex(embeddings, ids, encoder)
    if backend == "faiss_flat":
        index_path = artifacts_dir / "faiss.index"
        if not index_path.is_file():
            raise IndexUnavailable(f"missing {index_path}")
        try:
            import faiss
        except ImportError as exc:
            raise IndexUnavailable(f"faiss not importable: {exc}") from exc
        return FaissFlatIndex(faiss.read_index(str(index_path)), embeddings, ids, encoder)
    raise IndexUnavailable(f"unknown backend {backend!r}")
