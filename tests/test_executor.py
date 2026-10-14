"""Spec: IR and Execution Plan Specification §7, §8; SRS FR-12."""

from __future__ import annotations

import pytest

from cineverse.compiler.codegen import Instruction
from cineverse.compiler.driver import compile_text
from cineverse.compiler.ir import Capabilities
from cineverse.runtime.context import RuntimeContext
from cineverse.runtime.executor import ProgramError, execute, validate
from cineverse.runtime.semantic_index import IndexUnavailable, NumpyIndex
from tests.stub_encoder import StubEncoder


@pytest.fixture
def ctx(toy_catalog, runtime_cfg) -> RuntimeContext:
    enc = StubEncoder()
    texts = [str(t) for t in toy_catalog.column("embed_text")]
    return RuntimeContext(toy_catalog, NumpyIndex(enc.encode(texts), toy_catalog.all_ids(), enc),
                          enc, runtime_cfg, Capabilities(True, True))


def run(text, registry, ctx, optimize=False):
    comp = compile_text(text, registry, ctx.cfg, optimize=optimize)
    assert comp.ok, comp.diagnostics
    return execute(comp.program, ctx, ir=comp.ir)


def I(dest, op, *operands):  # noqa: E743
    return Instruction(dest, op, operands)


def test_unknown_opcode_rejected():
    assert any("unknown opcode" in e for e in validate([I("%a", "FLY"), I(None, "RET", "%a")]))


def test_use_before_definition_rejected():
    errors = validate([I("%t", "TOPK", "%r", 5), I(None, "RET", "%t")])
    assert any("used before definition" in e for e in errors)


def test_double_assignment_rejected():
    errors = validate([I("%s0", "SCAN"), I("%s0", "SCAN"), I(None, "RET", "%s0")])
    assert any("assigned twice" in e for e in errors)


def test_operand_type_mismatch_rejected():
    errors = validate([I("%s0", "SCAN"), I("%t", "TOPK", "%s0", 3), I(None, "RET", "%t")])
    assert any("TOPK expects" in e for e in errors)


def test_invalid_program_raises_and_executes_nothing(ctx):
    with pytest.raises(ProgramError):
        execute([I("%t", "TOPK", "%r", 5), I(None, "RET", "%t")], ctx)


def test_records_every_instruction(registry, ctx):
    exe = run("dark sci-fi after 2000", registry, ctx)
    assert [r["index"] for r in exe.execution] == list(range(len(exe.execution)))
    assert all({"opcode", "dest", "ms", "out_size", "sample", "status"} <= r.keys()
               for r in exe.execution)
    assert exe.ok and exe.results


def test_x201_when_index_missing(registry, ctx):
    no_index = RuntimeContext(ctx.catalog, None, None, ctx.cfg, ctx.caps)
    exe = run("comedy", registry, no_index)
    assert [d.code for d in exe.diagnostics] == ["X201"]
    assert next(r for r in exe.execution if r["opcode"] == "SEM_SEARCH")["status"] == "fallback"
    assert exe.results  # metadata-only results


def test_x201_when_index_raises(registry, ctx):
    class Broken:
        exact = True

        def search(self, text, scope, c):
            raise IndexUnavailable("gone")

    exe = run("comedy", registry, RuntimeContext(ctx.catalog, Broken(), None, ctx.cfg, ctx.caps))
    assert "X201" in [d.code for d in exe.diagnostics] and exe.ok


def test_x202_when_nothing_qualifies(registry, ctx):
    exe = run("only documentaries rated at least 5", registry, ctx)
    assert exe.results == [] and [d.code for d in exe.diagnostics] == ["X202"]


def test_partial_trace_on_unexpected_exception(registry, ctx, monkeypatch):
    import cineverse.runtime.executor as ex

    def boom(*a, **k):
        raise RuntimeError("kaput")

    monkeypatch.setattr(ex, "soft_score", boom)
    exe = run("comedy", registry, ctx)
    assert not exe.ok and "kaput" in exe.error
    assert exe.execution[-1]["status"] == "error" and exe.execution[-1]["opcode"] == "SOFT"


def test_hard_constraints_honoured(registry, ctx):
    exe = run("comedy after 2000, no romance", registry, ctx)
    for r in exe.results:
        rec = ctx.catalog.get(r.movie_id)
        assert rec.year is not None and rec.year > 2000 and "Romance" not in rec.genres
