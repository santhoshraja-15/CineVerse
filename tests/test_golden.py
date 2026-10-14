"""Stage outputs equal their golden files. Spec: Testing and Quality Assurance Plan §4."""

from __future__ import annotations

import difflib

import pytest

from tests.golden.common import GOLDEN, STAGES, dumps, golden_registry, items, path_for

CASES = [
    (stage, item)
    for stage in STAGES
    if (GOLDEN / stage).is_dir()
    for item in items()
]


@pytest.fixture(scope="module")
def reg():
    return golden_registry()


@pytest.mark.parametrize(("stage", "item"), CASES,
                         ids=[f"{s}-{i['id']}" for s, i in CASES])
def test_stage_matches_golden(stage, item, reg):
    target = path_for(stage, item["id"])
    assert target.exists(), f"missing {target}; run python -m tests.golden.regenerate"
    expected = target.read_text(encoding="utf-8")
    actual = dumps(STAGES[stage](item["text"], reg))
    if actual != expected:
        diff = "\n".join(difflib.unified_diff(expected.splitlines(), actual.splitlines(),
                                              "golden", "actual", lineterm="", n=1))
        pytest.fail(f"{stage}/{item['id']} differs from golden:\n{diff}")
