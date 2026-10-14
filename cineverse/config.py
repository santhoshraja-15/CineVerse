"""Load and validate config/registry.yaml and config/runtime.yaml into frozen dataclasses.

Spec: CineVerse_Configuration_and_Secrets_Management §2–§5.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

SUPPORTED_MAJOR = "1"
INDEX_BACKENDS = ("faiss_flat", "numpy")


class ConfigError(Exception):
    """Raised at start-up when a configuration file is missing or invalid; names the key path."""


@dataclass(frozen=True, slots=True)
class Paths:
    config_dir: Path
    data_dir: Path
    artifacts_dir: Path

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw" / "ml-latest-small"

    @property
    def catalog_path(self) -> Path:
        return self.data_dir / "processed" / "catalog.parquet"

    @property
    def manifest_path(self) -> Path:
        return self.artifacts_dir / "manifest.json"


def get_paths() -> Paths:
    """Resolve directories from CINEVERSE_* environment variables (Configuration §5)."""
    return Paths(
        config_dir=Path(os.environ.get("CINEVERSE_CONFIG_DIR", "config")),
        data_dir=Path(os.environ.get("CINEVERSE_DATA_DIR", "data")),
        artifacts_dir=Path(os.environ.get("CINEVERSE_ARTIFACTS_DIR", "artifacts")),
    )


# --------------------------------------------------------------------------- registry


@dataclass(frozen=True, slots=True)
class FieldSpec:
    name: str
    type: str
    ops: tuple[str, ...]
    available: bool
    unit: str | None
    domain: tuple[float | None, float | None] | str | None


@dataclass(frozen=True, slots=True)
class UnitSpec:
    name: str
    field: str
    factor: float


@dataclass(frozen=True, slots=True)
class LimitSpec:
    min: int
    max: int
    default: int


@dataclass(frozen=True, slots=True)
class RegistryConfig:
    registry_version: str
    genres: Mapping[str, str]  # canonical -> display name
    genre_aliases: Mapping[str, tuple[str, ...]]
    fields: Mapping[str, FieldSpec]
    units: Mapping[str, UnitSpec]
    limit: LimitSpec
    max_input_chars: int
    sha256: str


# --------------------------------------------------------------------------- runtime


@dataclass(frozen=True, slots=True)
class SoftConfig:
    beta: float
    lam: float
    mu: float


@dataclass(frozen=True, slots=True)
class MetadataConfig:
    tag_match_weight: float
    bayes_m: int


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    runtime_version: str
    model_name: str
    index_backend: str
    candidate_budget: int
    rrf_k: int
    score_round_decimals: int
    soft: SoftConfig
    metadata: MetadataConfig
    mmr_lambda: float
    seed: int
    sha256: str


# --------------------------------------------------------------------------- helpers


def _read_yaml(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        raise ConfigError(f"{path}: file not found")
    raw = path.read_bytes()
    try:
        data = yaml.safe_load(raw.decode("utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML ({exc})") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    return data, hashlib.sha256(raw).hexdigest()


def _req(data: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in data:
        raise ConfigError(f"{where}.{key}: required key missing")
    return data[key]


def _num(value: Any, where: str, lo: float | None = None, hi: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{where}: expected a number, got {value!r}")
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        raise ConfigError(f"{where}: {value} outside [{lo}, {hi}]")
    return value


def _check_version(value: Any, where: str) -> str:
    text = str(value)
    if text.split(".")[0] != SUPPORTED_MAJOR:
        raise ConfigError(f"{where}: unsupported major version {text!r}")
    return text


# --------------------------------------------------------------------------- loaders


def load_registry_config(path: Path | None = None) -> RegistryConfig:
    """Load registry.yaml; validate genres, aliases, fields, units and limits."""
    path = path or get_paths().config_dir / "registry.yaml"
    data, digest = _read_yaml(path)
    w = path.name

    version = _check_version(_req(data, "registry_version", w), f"{w}.registry_version")

    genres_raw = _req(data, "genres", w)
    if not isinstance(genres_raw, dict) or not genres_raw:
        raise ConfigError(f"{w}.genres: must be a non-empty mapping")
    genres = {str(k): str(v) for k, v in genres_raw.items()}
    if len({k.lower() for k in genres}) != len(genres):
        raise ConfigError(f"{w}.genres: canonical names must be unique")

    aliases: dict[str, tuple[str, ...]] = {}
    for lexeme, targets in (_req(data, "genre_aliases", w) or {}).items():
        if not isinstance(targets, list) or not targets:
            raise ConfigError(f"{w}.genre_aliases.{lexeme}: must be a non-empty list")
        for g in targets:
            if g not in genres:
                raise ConfigError(f"{w}.genre_aliases.{lexeme}: unknown genre {g!r}")
        aliases[str(lexeme)] = tuple(str(g) for g in targets)

    fields: dict[str, FieldSpec] = {}
    for name, spec in _req(data, "fields", w).items():
        where = f"{w}.fields.{name}"
        domain = spec.get("domain")
        if isinstance(domain, list):
            if len(domain) != 2:
                raise ConfigError(f"{where}.domain: expected [lo, hi]")
            domain = (domain[0], domain[1])
        elif domain is not None and domain != "from_catalog":
            raise ConfigError(f"{where}.domain: expected [lo, hi] or from_catalog")
        fields[str(name)] = FieldSpec(
            name=str(name),
            type=str(_req(spec, "type", where)),
            ops=tuple(str(o) for o in _req(spec, "ops", where)),
            available=bool(_req(spec, "available", where)),
            unit=spec.get("unit"),
            domain=domain,
        )

    units: dict[str, UnitSpec] = {}
    for name, spec in _req(data, "units", w).items():
        where = f"{w}.units.{name}"
        target = str(_req(spec, "field", where))
        if target not in fields:
            raise ConfigError(f"{where}.field: undeclared field {target!r}")
        units[str(name)] = UnitSpec(str(name), target, _num(_req(spec, "factor", where), where))

    lim = _req(data, "limit", w)
    limit = LimitSpec(
        min=int(_num(_req(lim, "min", f"{w}.limit"), f"{w}.limit.min", 1)),
        max=int(_num(_req(lim, "max", f"{w}.limit"), f"{w}.limit.max", 1)),
        default=int(_num(_req(lim, "default", f"{w}.limit"), f"{w}.limit.default", 1)),
    )
    if not limit.min <= limit.default <= limit.max:
        raise ConfigError(f"{w}.limit: require min <= default <= max")

    return RegistryConfig(
        registry_version=version,
        genres=MappingProxyType(genres),
        genre_aliases=MappingProxyType(aliases),
        fields=MappingProxyType(fields),
        units=MappingProxyType(units),
        limit=limit,
        max_input_chars=int(_num(_req(data, "max_input_chars", w), f"{w}.max_input_chars", 1)),
        sha256=digest,
    )


def load_runtime_config(path: Path | None = None) -> RuntimeConfig:
    """Load runtime.yaml; validate ranges and backend; apply CINEVERSE_INDEX_BACKEND."""
    path = path or get_paths().config_dir / "runtime.yaml"
    data, digest = _read_yaml(path)
    w = path.name

    backend = os.environ.get("CINEVERSE_INDEX_BACKEND") or _req(data, "index_backend", w)
    if backend not in INDEX_BACKENDS:
        raise ConfigError(f"{w}.index_backend: {backend!r} not in {INDEX_BACKENDS}")

    soft = _req(data, "soft", w)
    meta = _req(data, "metadata", w)
    mmr = data.get("mmr") or {}
    return RuntimeConfig(
        runtime_version=_check_version(_req(data, "runtime_version", w), f"{w}.runtime_version"),
        model_name=str(_req(data, "model_name", w)),
        index_backend=str(backend),
        candidate_budget=int(
            _num(_req(data, "candidate_budget", w), f"{w}.candidate_budget", 10, 2000)
        ),
        rrf_k=int(_num(_req(data, "rrf_k", w), f"{w}.rrf_k", 1)),
        score_round_decimals=int(
            _num(_req(data, "score_round_decimals", w), f"{w}.score_round_decimals", 0)
        ),
        soft=SoftConfig(
            beta=_num(_req(soft, "beta", f"{w}.soft"), f"{w}.soft.beta", 0, 1),
            lam=_num(_req(soft, "lambda", f"{w}.soft"), f"{w}.soft.lambda", 0, 1),
            mu=_num(_req(soft, "mu", f"{w}.soft"), f"{w}.soft.mu", 0, 1),
        ),
        metadata=MetadataConfig(
            tag_match_weight=_num(
                _req(meta, "tag_match_weight", f"{w}.metadata"),
                f"{w}.metadata.tag_match_weight",
                0,
                1,
            ),
            bayes_m=int(_num(_req(meta, "bayes_m", f"{w}.metadata"), f"{w}.metadata.bayes_m", 0)),
        ),
        mmr_lambda=_num(mmr.get("lambda", 0.7), f"{w}.mmr.lambda", 0, 1),
        seed=int(_num(_req(data, "seed", w), f"{w}.seed", 0)),
        sha256=digest,
    )
