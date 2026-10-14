"""Hard predicate evaluation: MASK over a movie set, FILTER_LIST over a ranked list.

Unknown values never satisfy a predicate. Spec: CineVerse_Recommendation_Engine_Specification
§2 (11.5), §2.1.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from cineverse.compiler.ir import Constraint
from cineverse.runtime.catalog import Catalog
from cineverse.runtime.context import RANK_KEYS, RankedList

_NUMERIC_OPS = {
    "<=": np.less_equal,
    ">=": np.greater_equal,
    "<": np.less,
    ">": np.greater,
}


def satisfied(catalog: Catalog, rows: np.ndarray, pred: Constraint) -> np.ndarray:
    """Boolean array over `rows` (catalogue row positions): does each movie satisfy `pred`?"""
    if pred.field == "genre":
        genres = catalog.column("genres")[rows]
        has = np.fromiter((pred.value in g for g in genres), dtype=bool, count=len(rows))
        return has if pred.op == "HAS" else ~has
    if not catalog.has_column(pred.field):
        return np.zeros(len(rows), dtype=bool)  # unavailable field: unknown => not satisfied
    col = catalog.column(pred.field)[rows]
    if pred.field == "language":
        return np.fromiter(
            (v is not None and v == pred.value for v in col), dtype=bool, count=len(rows)
        )
    values = col.astype(np.float64)
    known = ~np.isnan(values)
    with np.errstate(invalid="ignore"):
        ok = _NUMERIC_OPS[pred.op](values, float(pred.value))
    return known & ok


def _all_satisfied(catalog: Catalog, ids: np.ndarray, preds: Sequence[Constraint]) -> np.ndarray:
    keep = np.ones(len(ids), dtype=bool)
    if not preds or len(ids) == 0:
        return keep
    rows = catalog.rows(ids)
    for p in preds:
        keep &= satisfied(catalog, rows, p)
    return keep


def mask(catalog: Catalog, scope: np.ndarray, preds: Sequence[Constraint]) -> np.ndarray:
    """MASK: ids in `scope` (order kept) satisfying every predicate."""
    scope = np.asarray(scope, dtype=np.int64)
    return scope[_all_satisfied(catalog, scope, preds)]


def filter_list(
    catalog: Catalog, rl: RankedList, preds: Sequence[Constraint], c: int
) -> RankedList:
    """FILTER_LIST: keep order, drop failing movies, renumber ranks, truncate to c."""
    ids = np.asarray(rl.ids, dtype=np.int64)
    keep = np.flatnonzero(_all_satisfied(catalog, ids, preds))[:c]
    out_ids = tuple(int(ids[i]) for i in keep)
    evidence = {}
    for new_rank, mid in enumerate(out_ids, start=1):
        ev = dict(rl.evidence.get(mid, {}))
        for key in RANK_KEYS:
            if key in ev:
                ev[key] = new_rank
        evidence[mid] = ev
    return RankedList(out_ids, tuple(rl.scores[i] for i in keep), rl.source, evidence)
