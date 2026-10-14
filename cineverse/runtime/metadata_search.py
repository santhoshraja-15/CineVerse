"""Metadata search over genres and tags, and popularity ranking.

Spec: CineVerse_Recommendation_Engine_Specification §2 (11.3), §2.1.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from cineverse.runtime.catalog import Catalog
from cineverse.runtime.context import RankedList
from cineverse.runtime.fusion import ROUND
from cineverse.runtime.scoring import tag_match


def search(
    catalog: Catalog,
    genres: Sequence[str],
    terms: Sequence[str],
    scope: np.ndarray,
    c: int,
    *,
    tag_weight: float = 0.5,
) -> RankedList:
    """Keep movies with any genre or tag-term match; sort by
    (-genre_matches, -tag_term_matches, -bayes, movie_id); score = genres + w·tags."""
    if not genres and not terms:
        return RankedList.empty("metadata")
    scope = np.asarray(scope, dtype=np.int64)
    rows = catalog.rows(scope)
    all_genres, all_tags = catalog.column("genres"), catalog.column("tags")
    bayes = catalog.column("bayes")
    wanted = set(genres)

    hits = []
    for mid, r in zip(scope.tolist(), rows.tolist(), strict=True):
        g_hit = sorted(wanted.intersection(all_genres[r]))
        t_hit = []
        for term in terms:
            tag = tag_match(term, all_tags[r])
            if tag is not None:
                t_hit.append((term, tag))
        if g_hit or t_hit:
            key = (-len(g_hit), -len(t_hit), -round(float(bayes[r]), ROUND), mid)
            hits.append((key, mid, g_hit, t_hit))
    hits.sort(key=lambda h: h[0])
    hits = hits[:c]

    ids, scores, evidence = [], [], {}
    for rank, (_, mid, g_hit, t_hit) in enumerate(hits, start=1):
        ids.append(mid)
        scores.append(len(g_hit) + tag_weight * len(t_hit))
        evidence[mid] = {
            "metadata_rank": rank,
            "matched_genres": g_hit,
            "matched_tags": [list(t) for t in t_hit],
        }
    return RankedList(tuple(ids), tuple(scores), "metadata", evidence)


def popularity(catalog: Catalog, scope: np.ndarray, c: int) -> RankedList:
    """Rank the scope by (-round(bayes, 6), movie_id); score = bayes."""
    scope = np.asarray(scope, dtype=np.int64)
    if scope.size == 0:
        return RankedList.empty("popularity")
    rows = catalog.rows(scope)
    bayes = catalog.column("bayes")[rows].astype(np.float64)
    order = np.lexsort((scope, -np.round(bayes, ROUND)))[:c]
    rating, votes = catalog.column("rating"), catalog.column("votes")
    ids, scores, evidence = [], [], {}
    for rank, i in enumerate(order.tolist(), start=1):
        mid, r = int(scope[i]), int(rows[i])
        ids.append(mid)
        scores.append(float(bayes[i]))
        rv = float(rating[r])
        evidence[mid] = {
            "popularity_rank": rank,
            "bayes": float(bayes[i]),
            "rating": None if np.isnan(rv) else rv,
            "votes": int(votes[r]),
        }
    return RankedList(tuple(ids), tuple(scores), "popularity", evidence)
