"""Soft scoring: Score(d) = RRF(d)/Z + β·Σ m(p+) − λ·Σ m(p−) − μ·Σ v(c_soft).

Spec: CineVerse_Recommendation_Engine_Specification §2 (11.5), §3.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

import numpy as np

from cineverse.compiler.ir import Constraint, Preference
from cineverse.config import SoftConfig
from cineverse.runtime.catalog import Catalog
from cineverse.runtime.constraints import satisfied
from cineverse.runtime.context import RankedList
from cineverse.runtime.fusion import rank_key


def tag_match(term: str, tags: Sequence[str]) -> str | None:
    """First tag containing `term` as a whole word or phrase (Engine Spec §11.3), else None."""
    pattern = re.compile(rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])")
    return next((t for t in tags if pattern.search(t)), None)


def pref_match(pref: Preference, genres: Sequence[str], tags: Sequence[str]) -> str | None:
    """m(p, d): the matched genre or tag, or None."""
    if pref.kind == "genre":
        return pref.value if pref.value in genres else None
    return tag_match(pref.value, tags)


def soft_score(
    catalog: Catalog,
    rl: RankedList,
    prefs: Sequence[Preference],
    soft: Sequence[Constraint],
    cfg: SoftConfig,
) -> RankedList:
    """SOFT: add soft terms to the fused score and re-rank. Sums, not fractions."""
    if not rl.ids:
        return RankedList.empty("soft")
    ids = np.asarray(rl.ids, dtype=np.int64)
    rows = catalog.rows(ids)
    genres, tags = catalog.column("genres"), catalog.column("tags")
    sat = {i: satisfied(catalog, rows, c) for i, c in enumerate(soft)}

    scored: list[tuple[int, float]] = []
    evidence = {}
    for j, mid in enumerate(rl.ids):
        g, t = genres[rows[j]], tags[rows[j]]
        pos = [(p, pref_match(p, g, t)) for p in prefs if p.polarity == 1]
        neg = [(p, pref_match(p, g, t)) for p in prefs if p.polarity == -1]
        pos_hits = [(p.kind, p.value, hit) for p, hit in pos if hit]
        neg_hits = [(p.kind, p.value, hit) for p, hit in neg if hit]
        violated = [soft[i] for i in range(len(soft)) if not sat[i][j]]
        score = (
            rl.scores[j]
            + cfg.beta * len(pos_hits)
            - cfg.lam * len(neg_hits)
            - cfg.mu * len(violated)
        )
        scored.append((mid, score))
        ev = dict(rl.evidence.get(mid, {}))
        ev["soft"] = {
            "base": rl.scores[j],
            "pos_matches": [list(h) for h in pos_hits],
            "neg_matches": [list(h) for h in neg_hits],
            "violated": [c.model_dump(mode="json", exclude={"span"}) for c in violated],
        }
        evidence[mid] = ev
    scored.sort(key=lambda s: rank_key(s[1], s[0]))
    return RankedList(
        tuple(m for m, _ in scored), tuple(s for _, s in scored), "soft",
        {m: evidence[m] for m, _ in scored},
    )
