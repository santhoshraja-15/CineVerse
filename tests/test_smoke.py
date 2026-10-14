"""Every package and module imports. Spec: Testing and Quality Assurance Plan §3."""

from __future__ import annotations

import importlib
import pkgutil

import pytest

import cineverse

MODULES = sorted(
    m.name for m in pkgutil.walk_packages(cineverse.__path__, prefix="cineverse.")
)


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name: str) -> None:
    importlib.import_module(name)


def test_every_subpackage_found() -> None:
    for pkg in ("compiler", "runtime", "baseline", "data", "eval"):
        assert f"cineverse.{pkg}" in MODULES
