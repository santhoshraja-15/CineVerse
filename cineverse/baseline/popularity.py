"""B0: Bayesian-rating popularity over movies that pass the hard constraints.

Spec: CineVerse_Evaluation_and_Benchmarking_Plan §4.
"""

from __future__ import annotations

from collections.abc import Sequence

from cineverse.compiler.ir import Constraint
from cineverse.runtime import metadata_search
from cineverse.runtime.constraints import mask
from cineverse.runtime.context import RuntimeContext
from cineverse.runtime.explain import Recommendation, explain


def recommend_popularity(
    hard: Sequence[Constraint], limit: int, ctx: RuntimeContext
) -> list[Recommendation]:
    eligible = mask(ctx.catalog, ctx.catalog.all_ids(), hard)
    top = metadata_search.popularity(ctx.catalog, eligible, limit)
    return explain(ctx.catalog, top, None)
