"""Hand-wired reference recommender for the behaviour-preservation gate.

Calls runtime operators directly in canonical-plan order: exhaustive search → filter_list → rrf →
soft_score → top → explain. Imports only IR types from the compiler (LR-5).
Spec: CineVerse_Recommendation_Engine_Specification §5; Optimizer Spec §5.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cineverse.compiler.ir import Channels, CompiledQuery, Constraint, Output, Preference
from cineverse.runtime import metadata_search
from cineverse.runtime.constraints import filter_list
from cineverse.runtime.context import RankedList, RuntimeContext
from cineverse.runtime.explain import Recommendation, explain
from cineverse.runtime.fusion import rrf, z_for
from cineverse.runtime.scoring import soft_score


@dataclass
class BaselineSpec:
    semantic_text: str
    pos_genres: list[str]
    pos_terms: list[str]
    neg_soft: list[Preference]
    hard: list[Constraint]
    soft_constraints: list[Constraint]
    limit: int

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BaselineSpec:
        """Benchmark JSON (Database and Data Schemas §5); constraints there carry no span."""

        def con(c: dict[str, Any]) -> Constraint:
            return Constraint.model_validate({"span": (0, 0), **c})

        return cls(
            semantic_text=d["semantic_text"],
            pos_genres=list(d["pos_genres"]),
            pos_terms=list(d["pos_terms"]),
            neg_soft=[Preference.model_validate(p) for p in d["neg_soft"]],
            hard=[con(c) for c in d["hard"]],
            soft_constraints=[con(c) for c in d["soft_constraints"]],
            limit=int(d["limit"]),
        )

    def preferences(self) -> list[Preference]:
        """Soft preferences: positive genres that are not hard HAS, positive terms, negatives."""
        required = {c.value for c in self.hard if c.field == "genre" and c.op == "HAS"}
        prefs = [Preference(kind="genre", value=g, polarity=1)
                 for g in self.pos_genres if g not in required]
        prefs += [Preference(kind="text", value=t, polarity=1) for t in self.pos_terms]
        return prefs + list(self.neg_soft)

    def as_ir(self, semantic: bool) -> CompiledQuery:
        """An IR carrying the spec's meaning, for explanations only."""
        return CompiledQuery(
            source="",
            semantic_text=self.semantic_text,
            preferences=self.preferences(),
            constraints=self.hard + self.soft_constraints,
            channels=Channels(semantic=semantic),
            output=Output(limit=self.limit),
        )


def ranked_baseline(spec: BaselineSpec, ctx: RuntimeContext) -> RankedList:
    """The canonical pipeline up to TOPK (no explanations)."""
    catalog, cfg = ctx.catalog, ctx.cfg
    everything = catalog.all_ids()
    n, c = len(catalog), cfg.candidate_budget

    sources: list[RankedList] = []
    if ctx.index is not None:
        sources.append(ctx.index.search(spec.semantic_text, None, n))
    sources.append(
        metadata_search.search(
            catalog, spec.pos_genres, spec.pos_terms, everything, n,
            tag_weight=cfg.metadata.tag_match_weight,
        )
    )
    if not spec.pos_genres and not spec.pos_terms:
        sources.append(metadata_search.popularity(catalog, everything, n))

    filtered = [filter_list(catalog, rl, spec.hard, c) for rl in sources]
    fused = rrf(filtered, cfg.rrf_k, z_for(cfg.rrf_k))
    scored = soft_score(catalog, fused, spec.preferences(), spec.soft_constraints, cfg.soft)
    return scored.top(spec.limit)


def recommend_baseline(spec: BaselineSpec, ctx: RuntimeContext) -> list[Recommendation]:
    top = ranked_baseline(spec, ctx)
    return explain(ctx.catalog, top, spec.as_ir(ctx.index is not None))
