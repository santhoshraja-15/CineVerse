"""Spec: Dataset and Data Pipeline Specification §5, §9."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from cineverse.config import load_registry_config
from cineverse.data.build_index import build
from cineverse.data.prepare import prepare
from cineverse.runtime.semantic_index import open_index
from tests.stub_encoder import StubEncoder

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    base = tmp_path_factory.mktemp("idx")
    raw = base / "raw" / "ml-latest-small"
    shutil.copytree(ROOT / "tests" / "fixtures" / "toy_movielens", raw)
    catalog = base / "catalog.parquet"
    art = base / "artifacts"
    registry = load_registry_config(ROOT / "config" / "registry.yaml")
    prepare(raw, catalog, art / "manifest.json", registry, 10)
    return catalog, art


@pytest.mark.parametrize("backend", ["numpy", "faiss_flat"])
def test_build_writes_aligned_artifacts(built, backend, tmp_path):
    catalog, art = built
    out = tmp_path / backend
    shutil.copytree(art, out)
    build(catalog, out, backend, StubEncoder(), "stub-model", 42)
    emb, ids = np.load(out / "embeddings.npy"), np.load(out / "ids.npy")
    assert emb.dtype == np.float32 and ids.dtype == np.int64
    assert ids.tolist() == list(range(1, 9))
    assert np.allclose(np.linalg.norm(emb, axis=1), 1.0, atol=1e-5)
    assert (out / "faiss.index").exists() == (backend == "faiss_flat")
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["model"] == {"name": "stub-model", "dim": 8, "normalized": True}
    assert manifest["index"]["backend"] == backend and manifest["index"]["n"] == 8
    assert "catalog" in manifest  # prepare's sections are kept


def test_self_check_passes_and_backends_agree(built, tmp_path, capsys):
    catalog, art = built
    results = {}
    for backend in ("numpy", "faiss_flat"):
        out = tmp_path / backend
        shutil.copytree(art, out)
        build(catalog, out, backend, StubEncoder(), "stub", 42)
        assert "self-check 8/8" in capsys.readouterr().out
        idx = open_index(backend, out, StubEncoder())
        results[backend] = idx.search("anything", None, 8).ids
    assert results["numpy"] == results["faiss_flat"]
