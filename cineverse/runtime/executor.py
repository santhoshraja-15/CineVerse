"""Validating executor for SSA programs.

Validation (opcode known, def-before-use, single assignment, operand types) runs before anything
executes; a failure is a compiler bug and raises ProgramError. Failure policy while running:
SEM_SEARCH without an index/model -> X201 and an empty list; empty results -> X202; any other
exception stops execution with a partial trace.
Spec: CineVerse_IR_and_Execution_Plan_Specification §7; T01 review C1 (`ir` keyword).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from cineverse.compiler.codegen import Instruction
from cineverse.compiler.diagnostics import Diagnostic, make
from cineverse.compiler.ir import CompiledQuery
from cineverse.runtime import metadata_search
from cineverse.runtime.constraints import filter_list, mask
from cineverse.runtime.context import RankedList, RuntimeContext
from cineverse.runtime.embeddings import ModelUnavailable
from cineverse.runtime.explain import Recommendation, explain
from cineverse.runtime.fusion import rrf, z_for
from cineverse.runtime.scoring import soft_score
from cineverse.runtime.semantic_index import IndexUnavailable

log = logging.getLogger(__name__)

MOVIESET, RANKED, RESULTS = "MovieSet", "RankedList", "Results"
# opcode -> (register operand types in order, result type)
SIGNATURES: dict[str, tuple[tuple[str, ...], str | None]] = {
    "SCAN": ((), MOVIESET),
    "MASK": ((MOVIESET,), MOVIESET),
    "SEM_SEARCH": ((MOVIESET,), RANKED),
    "META_SEARCH": ((MOVIESET,), RANKED),
    "POP_RANK": ((MOVIESET,), RANKED),
    "FILTER_LIST": ((RANKED,), RANKED),
    "RRF": ((RANKED,), RANKED),  # one or more RankedList registers
    "SOFT": ((RANKED,), RANKED),
    "TOPK": ((RANKED,), RANKED),
    "EXPLAIN": ((RANKED,), RESULTS),
    "RET": ((RESULTS,), None),
}
SAMPLE = 5


class ProgramError(ValueError):
    """The program is malformed (a compiler bug); nothing was executed."""


@dataclass
class ExecutionResult:
    results: list[Recommendation]
    execution: list[dict[str, Any]]
    diagnostics: list[Diagnostic]
    ok: bool
    ms: float
    error: str | None = None
    trace: dict[str, Any] = field(default_factory=dict)


def _is_reg(x: Any) -> bool:
    return isinstance(x, str) and x.startswith("%")


def validate(program: list[Instruction]) -> list[str]:
    """Static checks of IR Spec §7 step 1; empty list = valid."""
    errors: list[str] = []
    types: dict[str, str | None] = {}
    for i, ins in enumerate(program):
        if ins.opcode not in SIGNATURES:
            errors.append(f"{i}: unknown opcode {ins.opcode}")
            continue
        wanted, result = SIGNATURES[ins.opcode]
        regs = [o for o in ins.operands if _is_reg(o)]
        for r in regs:
            if r not in types:
                errors.append(f"{i}: {r} used before definition")
        if ins.opcode == "RRF":
            bad = [r for r in regs if types.get(r) != RANKED]
            if not regs or bad:
                errors.append(f"{i}: RRF needs RankedList registers, got {regs}")
        elif ins.opcode == "RET":
            if len(regs) != 1 or types.get(regs[0]) not in (RESULTS, RANKED):
                errors.append(f"{i}: RET needs one Results or RankedList register")
        else:
            got = tuple(types.get(r) for r in regs)
            if got != wanted:
                errors.append(f"{i}: {ins.opcode} expects {wanted}, got {got}")
        if ins.dest is not None:
            if ins.dest in types:
                errors.append(f"{i}: {ins.dest} assigned twice")
            types[ins.dest] = result
    if not program or program[-1].opcode != "RET":
        errors.append("program does not end with RET")
    return errors


def _size(value: Any) -> int:
    return len(value) if value is not None else 0


def _sample(value: Any) -> list[int]:
    if isinstance(value, RankedList):
        return list(value.ids[:SAMPLE])
    if isinstance(value, np.ndarray):
        return [int(v) for v in value[:SAMPLE]]
    if isinstance(value, list):
        return [r.movie_id for r in value[:SAMPLE]]
    return []


def execute(
    program: list[Instruction], ctx: RuntimeContext, *, ir: CompiledQuery | None = None
) -> ExecutionResult:
    """Validate, then run each instruction in order, recording timings and samples."""
    errors = validate(program)
    if errors:
        raise ProgramError("; ".join(errors))

    catalog, cfg = ctx.catalog, ctx.cfg
    n_all = len(catalog)
    regs: dict[str, Any] = {}
    records: list[dict[str, Any]] = []
    diagnostics: list[Diagnostic] = []
    results: list[Recommendation] = []

    def c_of(c: Any) -> int:
        return n_all if c == "N" else int(c)

    def sem_search(text: str, scope: np.ndarray, c: Any) -> tuple[RankedList, str]:
        if ctx.index is None:
            return RankedList.empty("semantic"), "fallback"
        try:
            full = None if len(scope) == n_all else scope
            return ctx.index.search(text, full, c_of(c)), "ok"
        except (IndexUnavailable, ModelUnavailable) as exc:
            log.warning("semantic search unavailable: %s", exc)
            return RankedList.empty("semantic"), "fallback"

    ops: dict[str, Callable[..., Any]] = {
        "SCAN": lambda: catalog.all_ids(),
        "MASK": lambda scope, preds: mask(catalog, scope, preds),
        "META_SEARCH": lambda g, t, scope, c: metadata_search.search(
            catalog, list(g), list(t), scope, c_of(c), tag_weight=cfg.metadata.tag_match_weight),
        "POP_RANK": lambda scope, c: metadata_search.popularity(catalog, scope, c_of(c)),
        "FILTER_LIST": lambda rl, preds, c: filter_list(catalog, rl, preds, c_of(c)),
        "RRF": lambda *args: rrf(list(args[:-1]), args[-1], z_for(args[-1])),
        "SOFT": lambda rl, prefs, soft: soft_score(catalog, rl, list(prefs), list(soft), cfg.soft),
        "TOPK": lambda rl, n: rl.top(n),
        "EXPLAIN": lambda rl: explain(catalog, rl, ir),
    }

    t_start = time.perf_counter_ns()
    error: str | None = None
    for index, ins in enumerate(program):
        args = [regs[o] if _is_reg(o) else o for o in ins.operands]
        t0 = time.perf_counter_ns()
        status = "ok"
        try:
            if ins.opcode == "RET":
                value = args[0]
                results = value if isinstance(value, list) else explain(catalog, value, None)
            elif ins.opcode == "SEM_SEARCH":
                value, status = sem_search(*args)
                if status == "fallback" and not any(d.code == "X201" for d in diagnostics):
                    diagnostics.append(make("X201"))
            else:
                value = ops[ins.opcode](*args)
        except Exception as exc:  # failure policy: stop with a partial trace
            ms = (time.perf_counter_ns() - t0) / 1e6
            records.append({"index": index, "opcode": ins.opcode, "dest": ins.dest, "ms": ms,
                            "out_size": 0, "sample": [], "status": "error"})
            error = f"{ins.opcode} failed: {exc}"
            log.error("execution stopped at %d (%s): %s", index, ins.opcode, exc)
            break
        ms = (time.perf_counter_ns() - t0) / 1e6
        if ins.dest is not None:
            regs[ins.dest] = value
        if ins.opcode in ("MASK", "EXPLAIN") and _size(value) == 0 and status == "ok":
            status = "empty"
        records.append({"index": index, "opcode": ins.opcode, "dest": ins.dest, "ms": ms,
                        "out_size": _size(value) if ins.opcode != "RET" else len(results),
                        "sample": _sample(value), "status": status})

    if error is None and not results:
        diagnostics.append(make("X202"))
    total = (time.perf_counter_ns() - t_start) / 1e6
    return ExecutionResult(results, records, diagnostics, error is None, total, error)
