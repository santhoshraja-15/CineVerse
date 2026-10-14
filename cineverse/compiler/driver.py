"""Compiler driver: runs every stage in order, times it, and stops before planning on ERROR.

IR passes (O2, O1) always run, controlled by `rules`; `optimize` controls only the plan rules
(O3, O4) (T01 review C11). Until the optimizer tasks land, missing passes are identity.
Spec: CineVerse_IR_and_Execution_Plan_Specification §1; Flow Document F2; SRS FR-01, FR-05.3.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cineverse.compiler import optimizer as _optimizer
from cineverse.compiler import passes as _passes
from cineverse.compiler.ast import RequestNode, to_dict
from cineverse.compiler.codegen import Instruction, generate, print_program
from cineverse.compiler.diagnostics import Diagnostic, has_error, make
from cineverse.compiler.ir import Capabilities, CompiledQuery, DiagnosticModel, lower, validate
from cineverse.compiler.lexer import Token, lex
from cineverse.compiler.parser import parse
from cineverse.compiler.planner import LogicalPlan, build_plan
from cineverse.compiler.registry import DomainRegistry, load_registry
from cineverse.compiler.semantic import SemanticResult, analyse
from cineverse.config import RuntimeConfig, get_paths, load_runtime_config

ALL_RULES: frozenset[str] = frozenset({"O1", "O2", "O3", "O4"})
IR_RULES = ("O2", "O1")
PLAN_RULES = ("O3", "O4")
VALIDATOR_CODES = {"V1": "S105", "V2": "S103", "V3": "S107"}


@dataclass
class CompilationResult:
    source: str
    tokens: list[Token] = field(default_factory=list)
    ast: RequestNode | None = None
    semantic: SemanticResult | None = None
    ir_lowered: CompiledQuery | None = None
    ir: CompiledQuery | None = None
    plan_unoptimized: LogicalPlan | None = None
    plan: LogicalPlan | None = None
    rule_log: list[Any] = field(default_factory=list)
    program: list[Instruction] | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    ok: bool = False
    timings_ms: dict[str, float] = field(default_factory=dict)

    def printed_program(self) -> list[str]:
        return print_program(self.program) if self.program else []

    def to_trace_parts(self) -> dict[str, Any]:
        """Compile-side trace fields, serialised (Logging Spec §3)."""
        return {
            "source": self.source,
            "tokens": [t.to_dict() for t in self.tokens],
            "ast": to_dict(self.ast) if self.ast is not None else {},
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "ir_lowered": self.ir_lowered.model_dump(mode="json") if self.ir_lowered else None,
            "ir": self.ir.model_dump(mode="json") if self.ir else None,
            "rule_log": [r.to_dict() if hasattr(r, "to_dict") else r for r in self.rule_log],
            "plan_unoptimized": self.plan_unoptimized.to_dict() if self.plan_unoptimized else None,
            "plan": self.plan.to_dict() if self.plan else None,
            "program": self.printed_program(),
            "timings_ms": dict(self.timings_ms),
        }


class _Clock:
    def __init__(self) -> None:
        self.timings: dict[str, float] = {}

    def run(self, stage: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        t0 = time.perf_counter_ns()
        out = fn(*args, **kwargs)
        self.timings[stage] = (time.perf_counter_ns() - t0) / 1e6
        return out


def _ir_passes(ir: CompiledQuery, enabled: set[str]) -> tuple[CompiledQuery, list[Any]]:
    run = getattr(_passes, "run_ir_passes", None)
    return run(ir, enabled) if run is not None else (ir, [])


def _plan_rules(plan: LogicalPlan, ir: CompiledQuery, caps: Capabilities,
                enabled: set[str]) -> tuple[LogicalPlan, list[Any]]:
    run = getattr(_optimizer, "optimize", None)
    return run(plan, ir, caps, enabled) if run is not None else (plan, [])


def compile_text(
    text: str,
    registry: DomainRegistry,
    cfg: RuntimeConfig,
    *,
    optimize: bool = True,
    rules: frozenset[str] | set[str] = ALL_RULES,
) -> CompilationResult:
    """lex → parse → analyse → lower → passes → plan → optimize → codegen (Flow F2)."""
    clock = _Clock()
    result = CompilationResult(source=text)
    tokens, lex_diags = clock.run("lex", lex, text, registry)
    result.tokens = tokens
    result.diagnostics += lex_diags
    if has_error(lex_diags):  # S113
        result.timings_ms = clock.timings
        return result
    ast, parse_diags = clock.run("parse", parse, tokens, text)
    result.ast = ast
    result.diagnostics += parse_diags
    sem = clock.run("analyse", analyse, ast, registry)
    result.semantic = sem
    result.diagnostics += sem.diagnostics
    if has_error(result.diagnostics):  # LA-04: stop before planning
        result.timings_ms = clock.timings
        return result

    lowered = clock.run("lower", lower, sem, registry)
    lowered = lowered.model_copy(update={"diagnostics": [
        DiagnosticModel(**_diag_model(d)) for d in result.diagnostics]})
    result.ir_lowered = lowered
    ir, ir_log = clock.run("passes", _ir_passes, lowered, set(rules) & set(IR_RULES))
    result.ir, result.rule_log = ir, list(ir_log)
    canonical = "O2" in set(rules)  # V5 (sorted, <=/>= only) holds once O2 has run
    for error in validate(ir, registry, after_passes=canonical):
        code = VALIDATOR_CODES.get(error[:2])
        if code is None:
            raise AssertionError(f"compiler bug: {error}")
        result.diagnostics.append(make(code, None, None, **_validator_fields(code, error)))
    if has_error(result.diagnostics):
        result.timings_ms = clock.timings
        return result

    plan = clock.run("plan", build_plan, ir, cfg)
    result.plan_unoptimized = plan
    enabled = set(rules) & set(PLAN_RULES) if optimize else set()
    plan_opt, plan_log = clock.run("optimize", _plan_rules, plan, ir, registry.caps, enabled)
    result.plan = plan_opt
    result.rule_log += list(plan_log)
    problems = plan_opt.validate()
    if problems:
        raise AssertionError(f"compiler bug: invalid plan {problems}")
    result.program = clock.run("codegen", generate, plan_opt)
    result.ok = True
    result.timings_ms = clock.timings
    return result


def _diag_model(d: Diagnostic) -> dict[str, Any]:
    return {"code": d.code, "severity": d.severity.value, "message": d.message,
            "span": d.span, "hint": d.hint}


def _validator_fields(code: str, error: str) -> dict[str, str]:
    detail = error.split(":", 1)[1].strip()
    if code == "S105":
        return {"field": detail.split()[1], "text": detail}
    if code == "S103":
        parts = detail.split()
        return {"op": parts[1], "field": parts[-1]}
    return {"genre": detail.split()[0]}


def default_capabilities(artifacts_dir: Path) -> Capabilities:
    """Capabilities from artifacts on disk, for `compile()` without a RuntimeContext."""
    present = (artifacts_dir / "embeddings.npy").is_file() and (artifacts_dir / "ids.npy").is_file()
    return Capabilities(exact_search=True, semantic_available=present, mmr_available=False)


def compile(
    text: str, *, optimize: bool = True, rules: frozenset[str] | set[str] = ALL_RULES
) -> CompilationResult:
    """Compile with the project registry and runtime config (IR Spec §1 signature)."""
    paths = get_paths()
    registry = load_registry(default_capabilities(paths.artifacts_dir), paths)
    return compile_text(text, registry, load_runtime_config(), optimize=optimize, rules=rules)
