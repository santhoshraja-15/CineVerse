"""CineVerse: compiles natural-language movie requests into explainable recommendation plans.

    from cineverse import recommend
    comp, exe = recommend("no romance, after 2015", optimize=True)

Spec: CineVerse_UI_UX_and_API_Specification §3; IR and Execution Plan Specification §1.
"""

from __future__ import annotations

import functools
import hashlib
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cineverse.compiler.driver import CompilationResult
    from cineverse.compiler.registry import DomainRegistry
    from cineverse.runtime.context import RuntimeContext
    from cineverse.runtime.executor import ExecutionResult


@functools.lru_cache(maxsize=1)
def default_runtime() -> tuple[RuntimeContext, DomainRegistry]:
    """Catalogue, index, encoder, config and registry, loaded once per process."""
    from cineverse.compiler.registry import load_registry
    from cineverse.runtime.context import load_context

    ctx = load_context()
    return ctx, load_registry(ctx.caps)


def versions(ctx: RuntimeContext, registry: DomainRegistry) -> dict[str, Any]:
    from cineverse.config import get_paths

    manifest_path = get_paths().manifest_path
    dataset = "unknown"
    if manifest_path.is_file():
        import json

        files = json.loads(manifest_path.read_text("utf-8")).get("dataset", {}).get("files", {})
        joined = "".join(f.get("sha256", "") for _, f in sorted(files.items()))
        dataset = hashlib.sha256(joined.encode()).hexdigest()[:16] if joined else "unknown"
    return {"ir": "1.0", "registry": registry.config.registry_version,
            "registry_sha256": registry.config.sha256[:16], "runtime_sha256": ctx.cfg.sha256[:16],
            "dataset_sha256": dataset, "model": ctx.cfg.model_name}


def status() -> dict[str, Any]:
    """Facts for the UI footer and header: catalogue size, capabilities and versions."""
    ctx, registry = default_runtime()
    info = versions(ctx, registry)
    commit = "unknown"
    head = Path(".git/HEAD")
    if head.is_file():
        ref = head.read_text("utf-8").strip()
        if ref.startswith("ref: "):
            ref_path = Path(".git") / ref[5:]
            commit = ref_path.read_text("utf-8").strip()[:7] if ref_path.is_file() else "unknown"
        else:
            commit = ref[:7]
    return {**info, "catalog_rows": len(ctx.catalog), "semantic": ctx.caps.semantic_available,
            "exact_search": ctx.caps.exact_search, "commit": commit,
            "year_domain": registry.year_domain}


def recommend(
    text: str,
    *,
    optimize: bool = True,
    ctx: RuntimeContext | None = None,
    registry: DomainRegistry | None = None,
) -> tuple[CompilationResult, ExecutionResult | None]:
    """Compile and execute one request; returns (comp, None) when compilation fails."""
    from cineverse.compiler.driver import compile_text
    from cineverse.logging_setup import configure, request_logger
    from cineverse.runtime.executor import execute
    from cineverse.runtime.trace import build_trace, persist

    configure()
    if ctx is None or registry is None:
        default_ctx, default_reg = default_runtime()
        ctx, registry = ctx or default_ctx, registry or default_reg
    request_id = uuid.uuid4().hex[:12]
    log = request_logger("cineverse", request_id)
    log.info("request received (%d chars, optimize=%s)", len(text), optimize)

    comp = compile_text(text, registry, ctx.cfg, optimize=optimize)
    if not comp.ok:
        log.info("compile failed: %s", [d.code for d in comp.diagnostics])
        return comp, None
    exe = execute(comp.program or [], ctx, ir=comp.ir)
    exe.trace = build_trace(request_id, comp.to_trace_parts(), exe, versions(ctx, registry))
    log.info("executed %d results in %.1f ms", len(exe.results), exe.ms)
    if os.environ.get("CINEVERSE_PERSIST_TRACES") == "1":
        persist(exe.trace, Path("traces"))
    return comp, exe
