"""Layer dependency rules enforced on imports. Spec: Layer Architecture Requirements §2, §4."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN = {
    "cineverse.compiler": ["cineverse.runtime", "cineverse.baseline", "streamlit"],
    "cineverse.runtime": ["cineverse.compiler.lexer", "cineverse.compiler.parser",
                          "cineverse.compiler.ast", "cineverse.compiler.semantic",
                          "cineverse.compiler.passes", "cineverse.compiler.optimizer",
                          "streamlit"],
    "cineverse.baseline": ["cineverse.compiler.lexer", "cineverse.compiler.parser",
                           "cineverse.compiler.semantic", "cineverse.compiler.passes",
                           "cineverse.compiler.optimizer", "cineverse.compiler.planner"],
    "app": ["cineverse.compiler.lexer", "cineverse.compiler.parser",
            "cineverse.runtime.fusion", "cineverse.runtime.scoring"],
}
PURITY_EXEMPT = {"registry.py", "driver.py"}
PURITY_PATTERNS = [r"\bopen\(", r"\bimport random\b", r"\bfrom random\b", r"\btime\.",
                   r"os\.environ"]


def module_name(path: Path) -> str:
    return ".".join(path.relative_to(ROOT).with_suffix("").parts)


def imports_of(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append(node.module)
            found += [f"{node.module}.{a.name}" for a in node.names]
    return found


def python_files(package: str) -> list[Path]:
    base = ROOT.joinpath(*package.split("."))
    return sorted(base.rglob("*.py")) if base.exists() else []


CASES = [(pkg, p) for pkg in FORBIDDEN for p in python_files(pkg)]


@pytest.mark.parametrize(("package", "path"), CASES, ids=[str(p.name) for _, p in CASES])
def test_no_forbidden_imports(package: str, path: Path) -> None:
    """LR-1, LR-2, LR-4, LR-5."""
    bad = [
        imp for imp in imports_of(path)
        for prefix in FORBIDDEN[package]
        if imp == prefix or imp.startswith(prefix + ".")
    ]
    assert not bad, f"{module_name(path)} imports forbidden {sorted(set(bad))}"


@pytest.mark.parametrize("path", python_files("cineverse.compiler"),
                         ids=lambda p: p.name)
def test_compiler_stages_are_pure(path: Path) -> None:
    """LA-05: no file I/O, randomness, clocks or environment reads in the compiler."""
    if path.name in PURITY_EXEMPT:
        return
    text = path.read_text(encoding="utf-8")
    hits = [p for p in PURITY_PATTERNS if re.search(p, text)]
    assert not hits, f"{path.name} uses {hits}"


def test_only_prepare_reads_csv() -> None:
    """LR-6."""
    readers = [
        p for p in ROOT.joinpath("cineverse").rglob("*.py")
        if "read_csv" in p.read_text(encoding="utf-8")
    ]
    assert [p.name for p in readers] == ["prepare.py"]
