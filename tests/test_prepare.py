"""Tests for the catalogue preparation pipeline.

Spec: Dataset and Data Pipeline Specification §3–§4, §9.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from cineverse.config import load_registry_config
from cineverse.data.prepare import (
    CATALOG_SCHEMA,
    PrepareError,
    embed_text,
    normalise_tag,
    prepare,
    split_genres,
    split_title,
)

ROOT = Path(__file__).resolve().parents[1]
TOY = ROOT / "tests" / "fixtures" / "toy_movielens"
BAYES_M = 10
# Toy ratings after dropping the orphan (movie 99): 4, 5, 3, 0.5, 5, 4.5, 2, 3.5
GLOBAL_MEAN = 27.5 / 8


@pytest.fixture(scope="module")
def registry():
    return load_registry_config(ROOT / "config" / "registry.yaml")


@pytest.fixture
def raw_dir(tmp_path: Path) -> Path:
    dest = tmp_path / "raw" / "ml-latest-small"
    shutil.copytree(TOY, dest)
    return dest


def run(raw_dir: Path, registry, manifest: Path | None = None):
    out = raw_dir.parents[1] / "processed" / "catalog.parquet"
    manifest = manifest or raw_dir.parents[1] / "artifacts" / "manifest.json"
    report = prepare(raw_dir, out, manifest, registry, BAYES_M)
    return report, pd.read_parquet(out).set_index("movie_id"), out, manifest


# --------------------------------------------------------------------------- P4, P5, P7, P8 units


def test_split_title_strips_year_suffix():
    """Dataset Spec §3 P4."""
    assert split_title("Toy Film Alpha (1995)") == ("Toy Film Alpha", 1995)


def test_split_title_without_year_keeps_title_and_null_year():
    assert split_title("Toy Film Gamma") == ("Toy Film Gamma", None)


def test_split_title_keeps_alternative_name_before_year():
    expected = ("Toy Film Beta, The (Le Bêta)", 2001)
    assert split_title("Toy Film Beta, The (Le Bêta) (2001)") == expected


def test_split_title_tolerates_trailing_whitespace():
    assert split_title("Toy Film Delta (1987) ") == ("Toy Film Delta", 1987)


def test_split_title_year_range_is_not_a_year():
    assert split_title("Toy Film Eta (2006–2007)") == ("Toy Film Eta (2006–2007)", None)


def test_split_genres_pipe_and_no_genres():
    """Dataset Spec §3 P5."""
    assert split_genres("Sci-Fi|Mystery") == ["Sci-Fi", "Mystery"]
    assert split_genres("(no genres listed)") == []


def test_normalise_tag_strips_lowercases_and_collapses_spaces():
    """Dataset Spec §3 P7."""
    assert normalise_tag("  Mind   Bending ") == "mind bending"


def test_embed_text_uses_display_names_and_omits_empty_tags():
    """Dataset Spec §3 P8."""
    display = {"Sci-Fi": "science fiction", "Children": "children's"}
    expected = "X. Genres: science fiction. Tags: space."
    assert embed_text("X", ["Sci-Fi"], ["space"], display) == expected
    assert embed_text("X", ["Children"], [], display) == "X. Genres: children's."


# --------------------------------------------------------------------------- full pipeline


def test_prepare_writes_sorted_catalog_with_schema(raw_dir, registry):
    """Dataset Spec §3 P9; Database and Data Schemas §2."""
    report, cat, out, _ = run(raw_dir, registry)
    assert report.rows == 8
    assert list(cat.index) == sorted(cat.index)
    assert pq.read_schema(out).remove_metadata().equals(CATALOG_SCHEMA)


def test_prepare_parses_years_and_genres(raw_dir, registry):
    _, cat, _, _ = run(raw_dir, registry)
    assert cat.loc[2, "title"] == "Toy Film Beta, The (Le Bêta)"
    assert cat.loc[2, "year"] == 2001
    assert pd.isna(cat.loc[3, "year"])
    assert list(cat.loc[5, "genres"]) == []
    assert list(cat.loc[6, "genres"]) == ["Sci-Fi", "Mystery", "Thriller"]


def test_bayesian_rating_formula(raw_dir, registry):
    """Dataset Spec §3 P6: bayes = (v*R + m*C)/(v + m)."""
    _, cat, _, _ = run(raw_dir, registry)
    expected = (2 * 4.5 + BAYES_M * GLOBAL_MEAN) / (2 + BAYES_M)
    assert cat.loc[1, "votes"] == 2
    assert cat.loc[1, "rating"] == pytest.approx(4.5)
    assert cat.loc[1, "bayes"] == pytest.approx(expected, abs=1e-6)


def test_unrated_movie_has_null_rating_zero_votes_and_global_mean_bayes(raw_dir, registry):
    _, cat, _, _ = run(raw_dir, registry)
    assert pd.isna(cat.loc[3, "rating"])
    assert cat.loc[3, "votes"] == 0
    assert cat.loc[3, "bayes"] == pytest.approx(GLOBAL_MEAN, abs=1e-6)


def test_tags_normalised_deduplicated_top20_by_count_then_alpha(raw_dir, registry):
    """Dataset Spec §3 P7."""
    _, cat, _, _ = run(raw_dir, registry)
    tags = list(cat.loc[6, "tags"])
    assert len(tags) == 20
    assert tags[:2] == ["mind bending", "zebra"]
    assert tags[2:] == [f"tag{i:02d}" for i in range(1, 19)]
    assert list(cat.loc[1, "tags"]) == ["pixar"]


def test_embed_text_in_catalog(raw_dir, registry):
    _, cat, _, _ = run(raw_dir, registry)
    assert cat.loc[1, "embed_text"] == (
        "Toy Film Alpha. Genres: adventure, animation, children's. Tags: pixar."
    )
    assert cat.loc[5, "embed_text"] == "Toy Film Epsilon. Genres: ."


def test_orphans_dropped_and_counted(raw_dir, registry):
    """Dataset Spec §4 D3."""
    report, cat, _, manifest = run(raw_dir, registry)
    assert report.orphans_dropped == {"ratings": 1, "tags": 1, "links": 1}
    assert 99 not in cat.index
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["dataset"]["orphans_dropped"] == {"ratings": 1, "tags": 1}


def test_manifest_keys_match_schema(raw_dir, registry):
    """Database and Data Schemas §3."""
    _, _, _, manifest = run(raw_dir, registry)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["manifest_version"] == "1.0"
    assert set(data["dataset"]) == {"name", "downloaded", "files", "orphans_dropped"}
    assert set(data["dataset"]["files"]) == {"movies.csv", "ratings.csv", "tags.csv", "links.csv"}
    assert data["dataset"]["files"]["ratings.csv"]["rows"] == 9
    assert len(data["dataset"]["files"]["movies.csv"]["sha256"]) == 64
    assert set(data["catalog"]) == {"rows", "built", "prepare_version", "coverage"}
    assert set(data["catalog"]["coverage"]) == {"year", "rating", "tags", "genres"}


def test_manifest_keeps_existing_model_and_index_sections(raw_dir, registry, tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"model": {"name": "m"}, "index": {"n": 1}}), encoding="utf-8")
    run(raw_dir, registry, manifest)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["model"] == {"name": "m"} and data["index"] == {"n": 1}


# --------------------------------------------------------------------------- checks D1–D7


def test_d1_missing_column_aborts(raw_dir, registry):
    (raw_dir / "movies.csv").write_text("movieId,name,genres\n1,X (2000),Drama\n", encoding="utf-8")
    with pytest.raises(PrepareError, match=r"^D1"):
        run(raw_dir, registry)


def test_d1_missing_file_aborts(raw_dir, registry):
    (raw_dir / "tags.csv").unlink()
    with pytest.raises(PrepareError, match=r"^D1"):
        run(raw_dir, registry)


def test_d2_duplicate_movie_id_aborts(raw_dir, registry):
    with (raw_dir / "movies.csv").open("a", encoding="utf-8") as fh:
        fh.write("1,Duplicate (1999),Drama\n")
    with pytest.raises(PrepareError, match=r"^D2"):
        run(raw_dir, registry)


def test_d4_rating_out_of_range_aborts(raw_dir, registry):
    with (raw_dir / "ratings.csv").open("a", encoding="utf-8") as fh:
        fh.write("4,1,5.5,964982799\n")
    with pytest.raises(PrepareError, match=r"^D4"):
        run(raw_dir, registry)


def test_d5_unknown_genre_aborts(raw_dir, registry):
    with (raw_dir / "movies.csv").open("a", encoding="utf-8") as fh:
        fh.write("9,Toy Film Iota (2000),Superhero\n")
    with pytest.raises(PrepareError, match=r"^D5"):
        run(raw_dir, registry)


def test_d6_low_year_coverage_warns_but_writes(raw_dir, registry):
    """2 of 8 toy titles have no year (75% < 95%)."""
    report, cat, _, _ = run(raw_dir, registry)
    assert any(w.startswith("D6") for w in report.warnings)
    assert len(cat) == 8


def test_d7_row_count_drift_warns(raw_dir, registry, tmp_path):
    manifest = tmp_path / "manifest.json"
    previous = {"dataset": {"files": {"ratings.csv": {"sha256": "x", "rows": 100}}}}
    manifest.write_text(json.dumps(previous), encoding="utf-8")
    report, _, _, _ = run(raw_dir, registry, manifest)
    assert any(w.startswith("D7") and "ratings.csv" in w for w in report.warnings)
