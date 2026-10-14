"""Every trace validates against runtime/trace_schema.json. Spec: Logging Spec §3; SRS FR-18."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from cineverse import recommend
from cineverse.compiler.ir import Capabilities
from cineverse.runtime.context import RuntimeContext
from cineverse.runtime.semantic_index import NumpyIndex
from cineverse.runtime.trace import load_schema, persist
from tests.stub_encoder import StubEncoder

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = json.loads(
    (ROOT / "docs" / "CineVerse_Example_Requests_and_Expected_Outputs.json").read_text("utf-8")
)["examples"]
VALID = [e for e in EXAMPLES if e["expected"]["ok"]]


@pytest.fixture(scope="module")
def schema():
    return load_schema()


@pytest.fixture
def ctx(toy_catalog, runtime_cfg) -> RuntimeContext:
    enc = StubEncoder()
    texts = [str(t) for t in toy_catalog.column("embed_text")]
    return RuntimeContext(toy_catalog, NumpyIndex(enc.encode(texts), toy_catalog.all_ids(), enc),
                          enc, runtime_cfg, Capabilities(True, True))


@pytest.mark.parametrize("ex", VALID, ids=[e["id"] for e in VALID])
def test_trace_validates_for_example(ex, schema, ctx, registry, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # logs/ goes to tmp
    comp, exe = recommend(ex["text"], ctx=ctx, registry=registry)
    jsonschema.validate(exe.trace, schema)
    assert exe.trace["program"] == comp.printed_program()
    assert exe.trace["timings_ms"]["total"] >= exe.trace["timings_ms"]["execute"]


def test_failed_compile_returns_no_execution(ctx, registry, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    comp, exe = recommend("only horror and no horror", ctx=ctx, registry=registry)
    assert not comp.ok and exe is None


def test_persist_writes_request_file(ctx, registry, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _, exe = recommend("comedy", ctx=ctx, registry=registry)
    path = persist(exe.trace, tmp_path / "traces")
    assert json.loads(path.read_text("utf-8"))["request_id"] == exe.trace["request_id"]


def test_schema_rejects_bad_request_id(schema, ctx, registry, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _, exe = recommend("comedy", ctx=ctx, registry=registry)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(dict(exe.trace, request_id="not-hex"), schema)
