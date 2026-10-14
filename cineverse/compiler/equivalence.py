"""Equivalence harness: optimized and unoptimized programs must return identical results.

The compiler may not import the runtime (LR-1), so the caller injects the executor and the
eligible-set function; tests and evaluation pass `runtime.executor.execute` and
`runtime.constraints.mask`.
Spec: CineVerse_Optimizer_and_Equivalence_Testing_Specification §6.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from cineverse.compiler.driver import ALL_RULES, compile_text, now_ns
from cineverse.compiler.registry import DomainRegistry

ROUND = 6


@dataclass
class EquivalenceReport:
    request_id: str
    rules: frozenset[str]  # rules enabled in the optimized run
    same_ids: bool
    same_scores: bool  # after round(score, 6)
    same_hard_outcomes: bool  # set of eligible ids identical
    same_diagnostics: bool
    ms_unoptimized: float
    ms_optimized: float
    first_difference: str = ""

    @property
    def equivalent(self) -> bool:
        return self.same_ids and self.same_scores and self.same_hard_outcomes and \
            self.same_diagnostics


def check(
    text: str,
    ctx: Any,
    rules: frozenset[str] = ALL_RULES,
    *,
    registry: DomainRegistry,
    execute: Callable[..., Any],
    eligible: Callable[[Any, Any], set[int]],
    request_id: str = "",
) -> EquivalenceReport:
    """Compile `text` with no rules and with `rules`; execute both; compare."""
    plain = compile_text(text, registry, ctx.cfg, optimize=False, rules=frozenset())
    opt = compile_text(text, registry, ctx.cfg, optimize=True, rules=rules)
    if not (plain.ok and opt.ok):
        same = [d.code for d in plain.diagnostics] == [d.code for d in opt.diagnostics]
        return EquivalenceReport(request_id, frozenset(rules), same, same, same, same, 0.0, 0.0)

    t0 = now_ns()
    a = execute(plain.program, ctx, ir=plain.ir)
    t1 = now_ns()
    b = execute(opt.program, ctx, ir=opt.ir)
    t2 = now_ns()

    ids_a, ids_b = [r.movie_id for r in a.results], [r.movie_id for r in b.results]
    sc_a = [round(r.score, ROUND) for r in a.results]
    sc_b = [round(r.score, ROUND) for r in b.results]
    diff = ""
    pairs_a = list(zip(ids_a, sc_a, strict=True))
    pairs_b = list(zip(ids_b, sc_b, strict=True))
    for rank, (x, y) in enumerate(zip(pairs_a, pairs_b, strict=False), 1):
        if x != y:
            diff = f"rank {rank}: unoptimized {x} vs optimized {y}"
            break
    if not diff and len(ids_a) != len(ids_b):
        diff = f"lengths {len(ids_a)} vs {len(ids_b)}"
    codes_a = [d.code for d in plain.diagnostics + a.diagnostics]
    codes_b = [d.code for d in opt.diagnostics + b.diagnostics]
    return EquivalenceReport(
        request_id=request_id,
        rules=frozenset(rules),
        same_ids=ids_a == ids_b,
        same_scores=sc_a == sc_b,
        same_hard_outcomes=eligible(ctx, plain.ir) == eligible(ctx, opt.ir),
        same_diagnostics=codes_a == codes_b,
        ms_unoptimized=(t1 - t0) / 1e6,
        ms_optimized=(t2 - t1) / 1e6,
        first_difference=diff,
    )
