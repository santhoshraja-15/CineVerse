"""Reciprocal Rank Fusion with constant normalisation, and the shared ranking key.

Spec: CineVerse_Recommendation_Engine_Specification §2 (11.4); Repository Standards §5.
"""

from __future__ import annotations

from typing import Any

from cineverse.runtime.context import RankedList

ROUND = 6


def rank_key(score: float, movie_id: int) -> tuple[float, int]:
    """Every ranking sorts by (-round(score, 6), movie_id)."""
    return (-round(score, ROUND), movie_id)


def z_for(k: int) -> float:
    """Z = 2/(k+1): constant, independent of how many lists ran (makes O3 exact)."""
    return 2.0 / (k + 1)


def merge_evidence(target: dict[int, dict[str, Any]], rl: RankedList) -> None:
    for mid in rl.ids:
        target.setdefault(mid, {}).update(rl.evidence.get(mid, {}))


def rrf(lists: list[RankedList], k: int, z: float) -> RankedList:
    """RRF(d) = Σ_r 1/(k + rank_r(d)); output score = RRF(d)/z."""
    sums: dict[int, float] = {}
    evidence: dict[int, dict[str, Any]] = {}
    for rl in lists:
        for rank, mid in enumerate(rl.ids, start=1):
            sums[mid] = sums.get(mid, 0.0) + 1.0 / (k + rank)
        merge_evidence(evidence, rl)
    order = sorted(sums, key=lambda m: rank_key(sums[m] / z, m))
    for mid in order:
        evidence[mid]["rrf"] = sums[mid] / z
    return RankedList(
        tuple(order), tuple(sums[m] / z for m in order), "rrf", {m: evidence[m] for m in order}
    )
