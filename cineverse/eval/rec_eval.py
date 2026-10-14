"""Recommendation evaluation over the systems B0, B1, B2, Baseline, Compiled, Compiled+O.

Judgment-free metrics (hard-violation rate, soft satisfaction, evidence support, coverage) are
always computed. Graded metrics (P@10, R@10, NDCG@10, MRR) need benchmark/judgments.csv (human
task H2) and are reported as pending until it exists; nothing is estimated.
Spec: CineVerse_Evaluation_and_Benchmarking_Plan §3, §4, §6.
"""

from __future__ import annotations

import csv
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from cineverse.baseline.baseline import BaselineSpec, recommend_baseline
from cineverse.baseline.popularity import recommend_popularity
from cineverse.compiler.codegen import generate
from cineverse.compiler.driver import compile_text
from cineverse.compiler.ir import Constraint, Output
from cineverse.compiler.optimizer import optimize as optimize_plan
from cineverse.compiler.planner import build_plan
from cineverse.compiler.registry import DomainRegistry
from cineverse.eval.metrics import bootstrap_ci, mrr, ndcg_at_k, precision_at_k, recall_at_k
from cineverse.runtime import metadata_search
from cineverse.runtime.constraints import mask, satisfied
from cineverse.runtime.context import RuntimeContext
from cineverse.runtime.executor import execute
from cineverse.runtime.scoring import pref_match

K = 10
SYSTEMS = ("B0", "B1", "B2", "Baseline", "Compiled", "Compiled+O")
System = Callable[[dict[str, Any]], list[int]]


def systems(ctx: RuntimeContext, registry: DomainRegistry) -> dict[str, System]:
    catalog = ctx.catalog

    def spec_of(item: dict[str, Any]) -> BaselineSpec:
        return BaselineSpec.from_dict(item["baseline_spec"])

    def b0(item: dict[str, Any]) -> list[int]:
        spec = spec_of(item)
        return [r.movie_id for r in recommend_popularity(spec.hard, K, ctx)]

    def b1(item: dict[str, Any]) -> list[int]:
        spec = spec_of(item)
        eligible = mask(catalog, catalog.all_ids(), spec.hard)
        rl = metadata_search.search(catalog, spec.pos_genres, spec.pos_terms, eligible, K,
                                    tag_weight=ctx.cfg.metadata.tag_match_weight)
        return list(rl.ids)

    def b2(item: dict[str, Any]) -> list[int]:
        if ctx.index is None:
            return []
        return list(ctx.index.search(item["text"], None, K).ids)

    def baseline(item: dict[str, Any]) -> list[int]:
        spec = spec_of(item)
        spec.limit = K
        return [r.movie_id for r in recommend_baseline(spec, ctx)]

    def compiled(optimize: bool) -> System:
        """The compiled pipeline with the result count fixed at K for a fair comparison."""
        def run(item: dict[str, Any]) -> list[int]:
            comp = compile_text(item["text"], registry, ctx.cfg, optimize=optimize)
            if not comp.ok or comp.ir is None:
                return []
            ir = comp.ir.model_copy(update={"output": Output(limit=K)})
            plan = build_plan(ir, ctx.cfg)
            if optimize:
                plan, _ = optimize_plan(plan, ir, ctx.caps, {"O3", "O4"})
            return [r.movie_id for r in execute(generate(plan), ctx, ir=ir).results]
        return run

    return {"B0": b0, "B1": b1, "B2": b2, "Baseline": baseline,
            "Compiled": compiled(False), "Compiled+O": compiled(True)}


def hard_of(item: dict[str, Any]) -> list[Constraint]:
    return BaselineSpec.from_dict(item["baseline_spec"]).hard


def violations(ctx: RuntimeContext, ids: list[int], hard: list[Constraint]) -> int:
    """Results that violate a verifiable hard constraint (unknown value counts as violation)."""
    if not ids or not hard:
        return 0
    rows = ctx.catalog.rows(np.asarray(ids, dtype=np.int64))
    ok = np.ones(len(ids), dtype=bool)
    for c in hard:
        ok &= satisfied(ctx.catalog, rows, c)
    return int((~ok).sum())


def negative_hits(ctx: RuntimeContext, ids: list[int], item: dict[str, Any]) -> int:
    neg = BaselineSpec.from_dict(item["baseline_spec"]).neg_soft
    if not neg:
        return 0
    hits = 0
    for mid in ids:
        rec = ctx.catalog.get(mid)
        hits += any(pref_match(p, rec.genres, rec.tags) for p in neg)
    return hits


def load_judgments(path: Path) -> dict[str, dict[int, int]]:
    """request_id -> movie_id -> final grade (final_grade if present, else grade)."""
    if not path.is_file():
        return {}
    out: dict[str, dict[int, int]] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            grade = row.get("final_grade") or row["grade"]
            out.setdefault(row["request_id"], {})[int(row["movie_id"])] = int(grade)
    return out


def evaluate(
    items: list[dict[str, Any]],
    ctx: RuntimeContext,
    registry: DomainRegistry,
    judgments: dict[str, dict[int, int]],
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Rows of results/recommendation_metrics.csv (system, metric, k, value, n_requests)."""
    valid = [i for i in items if i["baseline_spec"] is not None]
    runners = systems(ctx, registry)
    rows: list[dict[str, Any]] = []
    for name in SYSTEMS:
        lists = {i["id"]: runners[name](i) for i in valid}
        returned = sum(len(v) for v in lists.values())
        viol = sum(violations(ctx, lists[i["id"]], hard_of(i)) for i in valid)
        neg = sum(negative_hits(ctx, lists[i["id"]], i) for i in valid)
        distinct = len({m for v in lists.values() for m in v})

        def add(metric: str, value: float | str, n: int, name: str = name) -> None:
            rows.append({"system": name, "metric": metric, "k": K, "value": value,
                         "n_requests": n})

        add("hard_violation_rate", round(viol / returned, 4) if returned else 0.0, len(valid))
        add("soft_satisfaction", round(1 - neg / returned, 4) if returned else 1.0, len(valid))
        add("coverage", round(distinct / len(ctx.catalog), 4), len(valid))
        judged = [i for i in valid if i["id"] in judgments]
        if not judged:
            for metric in ("precision", "recall", "ndcg", "mrr"):
                add(metric, "pending H2 judgments", 0)
            continue
        for metric, fn in (("precision", precision_at_k), ("recall", recall_at_k),
                           ("ndcg", ndcg_at_k)):
            values = [fn(lists[i["id"]], judgments[i["id"]], K) for i in judged]
            mean, lo, hi = bootstrap_ci(values, seed=seed)
            add(metric, f"{mean:.4f} [{lo:.4f}, {hi:.4f}]", len(judged))
        values = [mrr(lists[i["id"]], judgments[i["id"]]) for i in judged]
        mean, lo, hi = bootstrap_ci(values, seed=seed)
        add("mrr", f"{mean:.4f} [{lo:.4f}, {hi:.4f}]", len(judged))
    return rows


def pool(items: list[dict[str, Any]], ctx: RuntimeContext,
         registry: DomainRegistry) -> dict[str, list[int]]:
    """Union of the top 10 of B0, B1, B2 and Compiled per request (Evaluation Plan §3)."""
    runners = systems(ctx, registry)
    out: dict[str, list[int]] = {}
    for item in items:
        if item["baseline_spec"] is None:
            continue
        seen: dict[int, None] = {}
        for name in ("B0", "B1", "B2", "Compiled"):
            for mid in runners[name](item):
                seen.setdefault(mid, None)
        out[item["id"]] = sorted(seen)
    return out
