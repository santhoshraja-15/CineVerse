"""Convert the Example Requests JSON into benchmark/requests.jsonl (task T02).

Spec: CineVerse_Database_and_Data_Schemas §5; Claude Code Master Instructions T02.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "docs" / "CineVerse_Example_Requests_and_Expected_Outputs.json"
OUT = ROOT / "benchmark" / "requests.jsonl"
DEV_IDS = {f"EX{i:02d}" for i in range(1, 11)}


def baseline_spec(ir: dict) -> dict:
    """BaselineSpec from a gold IR (Database and Data Schemas §5)."""
    prefs = ir["preferences"]
    hard = [c for c in ir["constraints"] if c["strictness"] == "hard"]
    soft = [c for c in ir["constraints"] if c["strictness"] == "soft"]
    pos_genres = {p["value"] for p in prefs if p["kind"] == "genre" and p["polarity"] == 1}
    pos_genres |= {c["value"] for c in hard if c["field"] == "genre" and c["op"] == "HAS"}
    return {
        "semantic_text": ir["semantic_text"],
        "pos_genres": sorted(pos_genres),
        "pos_terms": sorted(
            p["value"] for p in prefs if p["kind"] == "text" and p["polarity"] == 1
        ),
        "neg_soft": [p for p in prefs if p["polarity"] == -1],
        "hard": hard,
        "soft_constraints": soft,
        "limit": ir["output"]["limit"],
    }


def convert(example: dict) -> dict:
    expected = example["expected"]
    ir = expected.get("ir")
    gold_ir = None
    if ir is not None:
        gold_ir = {k: v for k, v in ir.items() if k not in ("source", "diagnostics")}
    return {
        "id": example["id"],
        "split": "dev" if example["id"] in DEV_IDS else "test",
        "category": example["category"],
        "text": example["text"],
        "gold_ir": gold_ir,
        "gold_diagnostics": list(expected["diagnostics"]),
        "baseline_spec": baseline_spec(gold_ir) if gold_ir is not None else None,
    }


def main() -> int:
    data = json.loads(EXAMPLES.read_text(encoding="utf-8"))
    rows = [convert(ex) for ex in data["examples"]]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"wrote {len(rows)} items to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
