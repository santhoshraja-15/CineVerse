"""Domain registry: the symbol table of the request language.

Built from config/registry.yaml plus catalogue statistics and runtime capabilities. `build_registry`
is pure; `load_registry` reads the catalogue and manifest (the one compiler module allowed I/O).
Spec: CineVerse_Compiler_Frontend_Specification §2.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from cineverse.compiler.ir import Capabilities
from cineverse.config import FieldSpec, Paths, RegistryConfig, get_paths, load_registry_config

GENRE_SET = "genre_set"


def plural(word: str) -> str | None:
    """English plural of the last word of a genre name or alias, or None when unsuitable."""
    head, _, last = word.rpartition(" ")
    if len(last) < 3 or "'" in last or last.endswith(("s", "x", "ed")):
        return None
    if last.endswith("y") and last[-2] not in "aeiou":
        if last in ("funny", "scary", "family"):
            return None
        last = last[:-1] + "ies"
    else:
        last += "s"
    return f"{head} {last}" if head else last


@dataclass(frozen=True)
class DomainRegistry:
    config: RegistryConfig
    genre_lexemes: Mapping[str, tuple[str, ...]]  # lower-case phrase -> canonical genres
    year_domain: tuple[int, int]
    coverage: Mapping[str, float]
    caps: Capabilities

    @property
    def genres(self) -> Mapping[str, str]:
        return self.config.genres

    @property
    def max_input_chars(self) -> int:
        return self.config.max_input_chars

    def display(self, genre: str) -> str:
        return self.config.genres[genre]

    def field(self, name: str) -> FieldSpec | None:
        return self.config.fields.get(name)

    def available(self, name: str) -> bool:
        spec = self.config.fields.get(name)
        return bool(spec and spec.available)

    def domain(self, name: str) -> tuple[float | None, float | None]:
        spec = self.config.fields[name]
        if spec.domain == "from_catalog":
            return (float(self.year_domain[0]), float(self.year_domain[1]))
        if isinstance(spec.domain, tuple):
            return spec.domain
        return (None, None)


def genre_lexemes(config: RegistryConfig) -> dict[str, tuple[str, ...]]:
    """Names, display names, aliases and generated plurals -> canonical genres."""
    table: dict[str, tuple[str, ...]] = {}
    for canonical, display in config.genres.items():
        table.setdefault(canonical.lower(), (canonical,))
        table.setdefault(display.lower(), (canonical,))
    for alias, targets in config.genre_aliases.items():
        table.setdefault(alias.lower(), targets)
    for phrase, targets in list(table.items()):
        p = plural(phrase)
        if p:
            table.setdefault(p, targets)
    return table


def build_registry(
    config: RegistryConfig,
    *,
    year_domain: tuple[int, int],
    caps: Capabilities,
    coverage: Mapping[str, float] | None = None,
) -> DomainRegistry:
    return DomainRegistry(
        config=config,
        genre_lexemes=MappingProxyType(genre_lexemes(config)),
        year_domain=year_domain,
        coverage=MappingProxyType(dict(coverage or {})),
        caps=caps,
    )


def catalog_year_domain(catalog_path: Path) -> tuple[int, int]:
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    years = pq.read_table(catalog_path, columns=["year"]).column("year")
    lo, hi = pc.min(years).as_py(), pc.max(years).as_py()
    if lo is None or hi is None:
        raise ValueError(f"{catalog_path} has no years")
    return int(lo), int(hi)


def load_registry(caps: Capabilities, paths: Paths | None = None) -> DomainRegistry:
    """Registry from config, catalogue year range and manifest coverage."""
    paths = paths or get_paths()
    config = load_registry_config(paths.config_dir / "registry.yaml")
    coverage: dict[str, float] = {}
    if paths.manifest_path.is_file():
        manifest = json.loads(paths.manifest_path.read_text(encoding="utf-8"))
        coverage = dict(manifest.get("catalog", {}).get("coverage", {}))
    return build_registry(
        config, year_domain=catalog_year_domain(paths.catalog_path), caps=caps, coverage=coverage
    )
