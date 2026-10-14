"""Behaviour preservation gate: compiled (unoptimized) == hand-wired baseline.

Spec: Optimizer and Equivalence Testing Specification §5; SRS FR-19. The toy test runs everywhere;
the full test (real catalogue + index) is marked `full` and skipped when artifacts are absent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cineverse.baseline.baseline import BaselineSpec, recommend_baseline
from cineverse.compiler.driver import compile_text
from cineverse.compiler.ir import Capabilities
from cineverse.runtime.context import RuntimeContext
from cineverse.runtime.executor import execute
from cineverse.runtime.semantic_index import NumpyIndex
from tests.stub_encoder import StubEncoder

ROOT = Path(__file__).resolve().parents[1]
ITEMS = [
    json.loads(line)
    for line in (ROOT / "benchmark" / "requests.jsonl").read_text("utf-8").splitlines()
    if line.strip()
]
VALID = [i for i in ITEMS if i["baseline_spec"] is not None]
IDS = [i["id"] for i in VALID]


def same(ctx, registry, item) -> None:
    comp = compile_text(item["text"], registry, ctx.cfg, optimize=False)
    assert comp.ok, comp.diagnostics
    compiled = execute(comp.program, ctx, ir=comp.ir).results
    baseline = recommend_baseline(BaselineSpec.from_dict(item["baseline_spec"]), ctx)
    assert [r.movie_id for r in compiled] == [r.movie_id for r in baseline], item["id"]
    assert [round(r.score, 6) for r in compiled] == [round(r.score, 6) for r in baseline]


@pytest.fixture(scope="module")
def toy_ctx(runtime_cfg_module, toy_catalog_module) -> RuntimeContext:
    enc = StubEncoder()
    texts = [str(t) for t in toy_catalog_module.column("embed_text")]
    index = NumpyIndex(enc.encode(texts), toy_catalog_module.all_ids(), enc)
    return RuntimeContext(toy_catalog_module, index, enc, runtime_cfg_module,
                          Capabilities(True, True))


@pytest.mark.parametrize("item", VALID, ids=IDS)
def test_preservation_toy(item, toy_ctx, registry):
    same(toy_ctx, registry, item)


@pytest.mark.full
@pytest.mark.parametrize("item", VALID, ids=IDS)
def test_preservation_full(item, full_ctx):
    ctx, registry = full_ctx
    same(ctx, registry, item)
