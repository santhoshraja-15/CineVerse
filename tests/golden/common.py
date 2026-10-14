"""Stage outputs serialised for golden files. Spec: Testing and Quality Assurance Plan §4.

Uses a fixed registry (pinned snapshot year range, CORE capabilities) so golden files never depend
on local data.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cineverse.compiler.ast import to_dict
from cineverse.compiler.ir import Capabilities
from cineverse.compiler.lexer import lex
from cineverse.compiler.parser import parse
from cineverse.compiler.registry import DomainRegistry, build_registry
from cineverse.config import load_registry_config, load_runtime_config

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "golden"
BENCHMARK = ROOT / "benchmark" / "requests.jsonl"
CATALOG_YEARS = (1902, 2018)


def golden_registry() -> DomainRegistry:
    return build_registry(
        load_registry_config(ROOT / "config" / "registry.yaml"),
        year_domain=CATALOG_YEARS,
        caps=Capabilities(exact_search=True, semantic_available=True, mmr_available=False),
    )


def _cfg():
    return load_runtime_config(ROOT / "config" / "runtime.yaml")


def items() -> list[dict[str, Any]]:
    lines = BENCHMARK.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def stage_tokens(text: str, reg: DomainRegistry) -> Any:
    tokens, diags = lex(text, reg)
    return {"tokens": [t.to_dict() for t in tokens], "diagnostics": [d.to_dict() for d in diags]}


def stage_ast(text: str, reg: DomainRegistry) -> Any:
    ast, diags = parse(lex(text, reg)[0], text)
    return {"ast": to_dict(ast), "diagnostics": [d.to_dict() for d in diags]}


def stage_ir(text: str, reg: DomainRegistry) -> Any | None:
    """IR after passes; None until the driver exists."""
    try:
        from cineverse.compiler.driver import compile_text
    except ImportError:
        return None
    result = compile_text(text, reg, _cfg(), optimize=False)
    return None if result.ir is None else json.loads(result.ir.to_json())


def stage_program(text: str, reg: DomainRegistry) -> Any | None:
    """Printed unoptimized and optimized programs; None until the driver exists."""
    try:
        from cineverse.compiler.codegen import print_program
        from cineverse.compiler.driver import compile_text
    except ImportError:
        return None
    out: dict[str, list[str]] = {}
    for key, optimize in (("unoptimized", False), ("optimized", True)):
        result = compile_text(text, reg, _cfg(), optimize=optimize)
        if result.program is None:
            return {"ok": False}
        out[key] = print_program(result.program)
    return out


STAGES: dict[str, Callable[[str, DomainRegistry], Any]] = {
    "tokens": stage_tokens,
    "ast": stage_ast,
    "ir": stage_ir,
    "program": stage_program,
}


def dumps(data: Any) -> str:
    return json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def path_for(stage: str, item_id: str) -> Path:
    return GOLDEN / stage / f"{item_id}.json"
