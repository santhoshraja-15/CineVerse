"""Equivalence gate: optimized == unoptimized for every benchmark item, each rule alone and all.

Spec: Optimizer and Equivalence Testing Specification §6; SRS FR-10.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cineverse.compiler.equivalence import check
from cineverse.compiler.ir import Capabilities
from cineverse.runtime.constraints import mask
from cineverse.runtime.context import RuntimeContext
from cineverse.runtime.executor import execute
from cineverse.runtime.semantic_index import NumpyIndex
from tests.stub_encoder import StubEncoder

ROOT = Path(__file__).resolve().parents[1]
ITEMS = [json.loads(line) for line in
         (ROOT / "benchmark" / "requests.jsonl").read_text("utf-8").splitlines() if line.strip()]
RULE_SETS = [frozenset({"O1"}), frozenset({"O2"}), frozenset({"O3"}), frozenset({"O4"}),
             frozenset({"O1", "O2", "O3", "O4"})]
CASES = [(item, rules) for rules in RULE_SETS for item in ITEMS]
IDS = [f"{i['id']}-{'+'.join(sorted(r))}" for i, r in CASES]


def eligible(ctx, ir) -> set[int]:
    hard = [c for c in ir.constraints if c.strictness == "hard"]
    return set(mask(ctx.catalog, ctx.catalog.all_ids(), hard).tolist())


def assert_equivalent(ctx, registry, item, rules):
    report = check(item["text"], ctx, rules, registry=registry, execute=execute,
                   eligible=eligible, request_id=item["id"])
    assert report.equivalent, (f"{item['id']} rules={sorted(rules)}: ids={report.same_ids} "
                               f"scores={report.same_scores} hard={report.same_hard_outcomes} "
                               f"diags={report.same_diagnostics} {report.first_difference}")


@pytest.fixture(scope="module")
def toy_ctx(toy_catalog_module, runtime_cfg_module) -> RuntimeContext:
    enc = StubEncoder()
    texts = [str(t) for t in toy_catalog_module.column("embed_text")]
    index = NumpyIndex(enc.encode(texts), toy_catalog_module.all_ids(), enc)
    return RuntimeContext(toy_catalog_module, index, enc, runtime_cfg_module,
                          Capabilities(True, True))


@pytest.mark.parametrize(("item", "rules"), CASES, ids=IDS)
def test_equivalence_toy(item, rules, toy_ctx, registry):
    assert_equivalent(toy_ctx, registry, item, rules)


@pytest.mark.full
@pytest.mark.parametrize(("item", "rules"), CASES, ids=IDS)
def test_equivalence_full(item, rules, full_ctx):
    ctx, registry = full_ctx
    assert_equivalent(ctx, registry, item, rules)
