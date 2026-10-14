"""Tests for runtime catalogue access. Spec: Recommendation Engine Specification §2.1; Dataset Spec §9."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from cineverse.config import load_registry_config
from cineverse.data.prepare import prepare
from cineverse.runtime.catalog import Catalog, CatalogError

ROOT = Path(__file__).resolve().parents[1]
TOY = ROOT / "tests" / "fixtures" / "toy_movielens"


@pytest.fixture(scope="module")
def catalog_path(tmp_path_factory) -> Path:
    base = tmp_path_factory.mktemp("cat")
    raw = base / "raw" / "ml-latest-small"
    shutil.copytree(TOY, raw)
    out = base / "catalog.parquet"
    registry = load_registry_config(ROOT / "config" / "registry.yaml")
    prepare(raw, out, base / "manifest.json", registry, 10)
    return out


@pytest.fixture(scope="module")
def catalog(catalog_path) -> Catalog:
    return Catalog.load(catalog_path)


def test_all_ids_sorted_int64(catalog):
    ids = catalog.all_ids()
    assert ids.dtype == np.int64
    assert ids.tolist() == [1, 2, 3, 4, 5, 6, 7, 8]
    assert len(catalog) == 8


def test_get_returns_record(catalog):
    rec = catalog.get(6)
    assert rec.movie_id == 6
    assert rec.title == "Toy Film Zeta"
    assert rec.year == 2016
    assert rec.genres == ("Sci-Fi", "Mystery", "Thriller")
    assert rec.votes == 3
    assert rec.rating == pytest.approx(10.0 / 3, abs=1e-5)


def test_get_unknown_values_are_none(catalog):
    rec = catalog.get(3)
    assert rec.year is None
    assert rec.rating is None
    assert rec.votes == 0


def test_get_unknown_id_raises(catalog):
    with pytest.raises(KeyError):
        catalog.get(999)


def test_column_aligned_with_all_ids(catalog):
    years = catalog.column("year")
    assert years.shape == catalog.all_ids().shape
    assert years[0] == 1995
    assert np.isnan(years[2])
    assert catalog.column("genres")[4] == ()


def test_column_unknown_name_raises(catalog):
    with pytest.raises(KeyError):
        catalog.column("runtime")


def test_rows_maps_ids_to_positions(catalog):
    assert catalog.rows(np.array([8, 1])).tolist() == [7, 0]


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(CatalogError):
        Catalog.load(tmp_path / "nope.parquet")


def test_load_missing_column_raises(tmp_path):
    path = tmp_path / "bad.parquet"
    pq.write_table(pa.table({"movie_id": pa.array([1], pa.int32())}), path)
    with pytest.raises(CatalogError, match="missing columns"):
        Catalog.load(path)
