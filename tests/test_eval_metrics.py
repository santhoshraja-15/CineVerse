"""Hand-computed checks for evaluation metrics. Spec: Evaluation and Benchmarking Plan §5, §6."""

from __future__ import annotations

import math

import pytest

from cineverse.eval.compiler_eval import slots
from cineverse.eval.metrics import (
    bootstrap_ci,
    micro_f1,
    mrr,
    ndcg_at_k,
    percentile,
    precision_at_k,
    prf,
    recall_at_k,
)

GRADES = {1: 2, 2: 0, 3: 1, 4: 2, 5: 0}  # pooled judgments for one request


def test_precision_at_k():
    assert precision_at_k([1, 2, 3, 9], GRADES, k=4) == 0.5  # 1 and 3 relevant


def test_recall_at_k():
    assert recall_at_k([1, 2, 3], GRADES, k=3) == pytest.approx(2 / 3)  # 3 relevant in pool


def test_recall_with_no_relevant_is_zero():
    assert recall_at_k([1], {1: 0}, k=1) == 0.0


def test_ndcg_hand_example():
    # ranked gains [2, 0, 1]; ideal [2, 2, 1]
    dcg = 2 + 0 / math.log2(3) + 1 / math.log2(4)
    ideal = 2 + 2 / math.log2(3) + 1 / math.log2(4)
    assert ndcg_at_k([1, 2, 3], GRADES, k=3) == pytest.approx(dcg / ideal)


def test_ndcg_perfect_ranking_is_one():
    assert ndcg_at_k([1, 4, 3, 2, 5], GRADES, k=5) == pytest.approx(1.0)


def test_mrr_first_grade_two():
    assert mrr([2, 3, 4, 1], GRADES) == pytest.approx(1 / 3)
    assert mrr([2, 3], GRADES) == 0.0


def test_micro_f1():
    p, r, f = micro_f1([prf({"a", "b"}, {"a"}), prf({"c"}, {"c", "d"})])
    assert (p, r) == (pytest.approx(2 / 3), pytest.approx(2 / 3)) and f == pytest.approx(2 / 3)


def test_bootstrap_is_seeded_and_brackets_the_mean():
    values = [0.1, 0.4, 0.5, 0.9, 0.3]
    a, b = bootstrap_ci(values), bootstrap_ci(values)
    assert a == b and a[1] <= a[0] <= a[2]


def test_percentile_nearest_rank():
    assert percentile([5, 1, 3, 2, 4], 50) == 3 and percentile([5, 1, 3, 2, 4], 95) == 5


def test_slots_include_limit_and_strictness():
    ir = {"preferences": [{"kind": "genre", "value": "Comedy", "polarity": 1}],
          "constraints": [{"field": "year", "op": ">=", "value": 2011, "strictness": "hard"}],
          "output": {"limit": 5}}
    assert slots(ir) == {("pref", "genre", "Comedy", 1), ("con", "year", ">=", "2011", "hard"),
                         ("limit", 5)}
