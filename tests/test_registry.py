"""Spec: Compiler Front-End Specification §2, §9; SRS FR-04."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from cineverse.compiler.ir import Capabilities
from cineverse.compiler.registry import build_registry, load_registry, plural
from cineverse.config import Paths, load_registry_config
from cineverse.data.prepare import prepare

ROOT = Path(__file__).resolve().parents[1]
CAPS = Capabilities(exact_search=True, semantic_available=True)


def test_canonical_names_display_names_and_aliases_resolve(registry):
    lex = registry.genre_lexemes
    assert lex["sci-fi"] == ("Sci-Fi",)
    assert lex["science fiction"] == ("Sci-Fi",)
    assert lex["children's"] == ("Children",)
    assert lex["rom-com"] == ("Romance", "Comedy")


@pytest.mark.parametrize(
    ("word", "genre"),
    [("comedies", "Comedy"), ("thrillers", "Thriller"), ("mysteries", "Mystery"),
     ("documentaries", "Documentary"), ("cartoons", "Animation"), ("rom-coms", "Romance")],
)
def test_plurals_generated(registry, word, genre):
    assert genre in registry.genre_lexemes[word]


def test_adjective_aliases_get_no_plural():
    assert plural("funny") is None and plural("animated") is None and plural("kids") is None


def test_runtime_and_language_unavailable_in_core(registry):
    assert not registry.available("runtime") and not registry.available("language")
    assert registry.available("year") and registry.available("genre")


def test_year_domain_from_catalogue_stats(registry):
    assert registry.domain("year") == (1902.0, 2018.0)
    assert registry.domain("rating") == (0.5, 5.0)
    assert registry.domain("votes") == (0, None)


def test_display_names(registry):
    assert registry.display("Sci-Fi") == "science fiction"
    assert registry.display("Film-Noir") == "film noir"


def test_capabilities_carried(registry):
    assert registry.caps.semantic_available and not registry.caps.mmr_available


def test_fields_not_hard_coded_unknown_field_is_none(registry):
    assert registry.field("budget") is None


def test_load_registry_reads_catalogue_and_manifest(tmp_path):
    raw = tmp_path / "data" / "raw" / "ml-latest-small"
    shutil.copytree(ROOT / "tests" / "fixtures" / "toy_movielens", raw)
    paths = Paths(config_dir=ROOT / "config", data_dir=tmp_path / "data",
                  artifacts_dir=tmp_path / "artifacts")
    config = load_registry_config(ROOT / "config" / "registry.yaml")
    prepare(raw, paths.catalog_path, paths.manifest_path, config, 10)
    reg = load_registry(CAPS, paths)
    assert reg.year_domain == (1962, 2016)  # toy catalogue years
    manifest = json.loads(paths.manifest_path.read_text(encoding="utf-8"))
    assert dict(reg.coverage) == manifest["catalog"]["coverage"]


def test_registry_is_immutable():
    reg = build_registry(load_registry_config(ROOT / "config" / "registry.yaml"),
                         year_domain=(1900, 2000), caps=CAPS)
    with pytest.raises(TypeError):
        reg.genre_lexemes["new"] = ("Drama",)  # type: ignore[index]
