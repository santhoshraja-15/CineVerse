"""Ranking and set metrics with bootstrap confidence intervals.

Spec: CineVerse_Evaluation_and_Benchmarking_Plan §5, §6.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence


def precision_at_k(ranked: Sequence[int], grades: dict[int, int], k: int = 10) -> float:
    """Relevant (grade >= 1) in the top k / k."""
    return sum(1 for m in ranked[:k] if grades.get(m, 0) >= 1) / k


def recall_at_k(ranked: Sequence[int], grades: dict[int, int], k: int = 10) -> float:
    """Relevant in the top k / relevant in the pool (0 when the pool has none)."""
    relevant = sum(1 for g in grades.values() if g >= 1)
    if relevant == 0:
        return 0.0
    return sum(1 for m in ranked[:k] if grades.get(m, 0) >= 1) / relevant


def ndcg_at_k(ranked: Sequence[int], grades: dict[int, int], k: int = 10) -> float:
    """Graded gains (0/1/2), log2 discount, ideal ranking from the pool."""
    def dcg(gains: Sequence[int]) -> float:
        return sum(g / math.log2(i + 2) for i, g in enumerate(gains))

    ideal = dcg(sorted(grades.values(), reverse=True)[:k])
    if ideal == 0:
        return 0.0
    return dcg([grades.get(m, 0) for m in ranked[:k]]) / ideal


def mrr(ranked: Sequence[int], grades: dict[int, int]) -> float:
    """1 / rank of the first grade-2 movie (0 if none)."""
    for i, m in enumerate(ranked, start=1):
        if grades.get(m, 0) == 2:
            return 1.0 / i
    return 0.0


def prf(predicted: set[object], gold: set[object]) -> tuple[int, int, int]:
    """True positives, predicted count, gold count (for micro-averaging)."""
    return len(predicted & gold), len(predicted), len(gold)


def micro_f1(counts: Sequence[tuple[int, int, int]]) -> tuple[float, float, float]:
    tp = sum(c[0] for c in counts)
    pred = sum(c[1] for c in counts)
    gold = sum(c[2] for c in counts)
    p = tp / pred if pred else 1.0
    r = tp / gold if gold else 1.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def bootstrap_ci(
    values: Sequence[float],
    stat: Callable[[Sequence[float]], float] = lambda v: sum(v) / len(v),
    resamples: int = 1000,
    seed: int = 42,
    alpha: float = 0.05,
) -> tuple[float, float, float]:
    """Mean and 95% percentile bootstrap interval over requests (seeded)."""
    if not values:
        return (float("nan"),) * 3
    rng = random.Random(seed)
    n = len(values)
    stats = sorted(stat([values[rng.randrange(n)] for _ in range(n)]) for _ in range(resamples))
    lo = stats[int(alpha / 2 * resamples)]
    hi = stats[min(resamples - 1, int((1 - alpha / 2) * resamples))]
    return stat(values), lo, hi


def percentile(values: Sequence[float], q: float) -> float:
    """Nearest-rank percentile (q in 0..100)."""
    if not values:
        return float("nan")
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return ordered[rank - 1]
