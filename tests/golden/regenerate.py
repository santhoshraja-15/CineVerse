"""Regenerate golden files and report every diff (the only way golden files change).

Usage: python -m tests.golden.regenerate --only tokens --only ast
Spec: Testing and Quality Assurance Plan §4; Master Instructions T13.
"""

from __future__ import annotations

import argparse
import difflib

from tests.golden.common import STAGES, dumps, golden_registry, items, path_for


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", action="append", choices=sorted(STAGES), default=None)
    args = parser.parse_args(argv)
    stages = args.only or list(STAGES)
    reg = golden_registry()
    for stage in stages:
        changed = 0
        all_items = items()
        for item in all_items:
            data = STAGES[stage](item["text"], reg)
            if data is None:
                print(f"{stage}: stage not implemented yet, skipped")
                break
            target = path_for(stage, item["id"])
            new = dumps(data)
            old = target.read_text(encoding="utf-8") if target.exists() else None
            if old != new:
                target.parent.mkdir(parents=True, exist_ok=True)
                if old is not None:
                    changed += 1
                    print(f"--- {stage}/{item['id']} changed:")
                    diff = difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="",
                                                n=1)
                    print("\n".join(list(diff)[2:]))
                target.write_text(new, encoding="utf-8", newline="\n")
        else:
            print(f"{stage}: {len(all_items)} files, {changed} changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
