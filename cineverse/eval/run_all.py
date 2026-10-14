"""Regenerate every results file with one command.

    python -m cineverse.eval.run_all [--quick] [--freeze-split]

Writes results/compiler_metrics.csv, equivalence.csv, recommendation_metrics.csv, latency.csv,
latency_summary.json and run_manifest.json. Refuses to run if the frozen test split changed.
Plots are not produced: no plotting library is in the approved stack.
Spec: CineVerse_Evaluation_and_Benchmarking_Plan §2, §8, §9; Database and Data Schemas §7.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cineverse import default_runtime
from cineverse.compiler.equivalence import check
from cineverse.config import get_paths
from cineverse.eval import compiler_eval, latency, rec_eval
from cineverse.runtime.constraints import mask
from cineverse.runtime.executor import execute

RESULTS = Path("results")
BENCHMARK = Path("benchmark/requests.jsonl")
FREEZE = Path("benchmark/split_freeze.json")
EXAMPLES = Path("docs/CineVerse_Example_Requests_and_Expected_Outputs.json")
RULE_SETS = [("O1",), ("O2",), ("O3",), ("O4",), ("O1", "O2", "O3", "O4")]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_split_hash(items: list[dict[str, Any]]) -> str:
    test = [json.dumps(i, sort_keys=True) for i in items if i["split"] == "test"]
    return hashlib.sha256("\n".join(test).encode("utf-8")).hexdigest()


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        if not rows:
            return
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def eligible(ctx: Any, ir: Any) -> set[int]:
    hard = [c for c in ir.constraints if c.strictness == "hard"]
    return set(mask(ctx.catalog, ctx.catalog.all_ids(), hard).tolist())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="10 compile / 3 execution runs")
    parser.add_argument("--freeze-split", action="store_true", help="record the test split hash")
    args = parser.parse_args(argv)

    items = [json.loads(line) for line in BENCHMARK.read_text("utf-8").splitlines() if line]
    split_hash = test_split_hash(items)
    if args.freeze_split:
        FREEZE.write_text(json.dumps({"test_split_sha256": split_hash}, indent=2) + "\n", "utf-8")
        print(f"test split frozen: {split_hash[:16]}…")
    frozen = json.loads(FREEZE.read_text("utf-8"))["test_split_sha256"] if FREEZE.is_file() \
        else None
    if frozen is not None and frozen != split_hash:
        print("REFUSED: the test split changed after it was frozen (Evaluation Plan §2).")
        return 1

    ctx, registry = default_runtime()
    examples = json.loads(EXAMPLES.read_text("utf-8"))["examples"]
    RESULTS.mkdir(exist_ok=True)

    print("compiler metrics…")
    rows = compiler_eval.evaluate(items, registry, ctx.cfg, Path("tests/golden/ast"), examples)

    print("equivalence and preservation…")
    eq_rows = []
    for rules in RULE_SETS:
        for item in items:
            r = check(item["text"], ctx, frozenset(rules), registry=registry, execute=execute,
                      eligible=eligible, request_id=item["id"])
            eq_rows.append({"request_id": item["id"], "rules": "+".join(rules),
                            "same_ids": r.same_ids, "same_scores": r.same_scores,
                            "same_hard_outcomes": r.same_hard_outcomes,
                            "same_diagnostics": r.same_diagnostics,
                            "ms_unoptimized": round(r.ms_unoptimized, 3),
                            "ms_optimized": round(r.ms_optimized, 3)})
    equivalent = sum(all(r[k] for k in ("same_ids", "same_scores", "same_hard_outcomes",
                                         "same_diagnostics")) for r in eq_rows)
    rows.append({"metric": "equivalence", "split": "all", "value": equivalent / len(eq_rows),
                 "n": len(eq_rows), "target": 1.0, "passed": equivalent == len(eq_rows)})
    from cineverse.baseline.baseline import BaselineSpec, recommend_baseline
    from cineverse.compiler.driver import compile_text

    valid = [i for i in items if i["baseline_spec"] is not None]
    preserved = 0
    for item in valid:
        comp = compile_text(item["text"], registry, ctx.cfg, optimize=False)
        a = execute(comp.program or [], ctx, ir=comp.ir).results
        b = recommend_baseline(BaselineSpec.from_dict(item["baseline_spec"]), ctx)
        preserved += [(r.movie_id, round(r.score, 6)) for r in a] == \
                     [(r.movie_id, round(r.score, 6)) for r in b]
    rows.append({"metric": "preservation", "split": "all", "value": preserved / len(valid),
                 "n": len(valid), "target": 1.0, "passed": preserved == len(valid)})

    print("latency…")
    runs = (10, 3) if args.quick else (100, 20)
    lat_rows = latency.measure(items, ctx, registry, compile_runs=runs[0], exec_runs=runs[1])
    summary = latency.summarise(lat_rows, ctx, registry, items)
    rows.append({"metric": "compile_latency_p95_ms", "split": "all",
                 "value": round(summary["compile_p95_ms"], 3),
                 "n": len(valid), "target": "< 50", "passed": summary["compile_p95_ms"] < 50})

    print("recommendation metrics…")
    judgments = rec_eval.load_judgments(Path("benchmark/judgments.csv"))
    rec_rows = rec_eval.evaluate(items, ctx, registry, judgments, seed=ctx.cfg.seed)

    write_csv(RESULTS / "compiler_metrics.csv", rows)
    write_csv(RESULTS / "equivalence.csv", eq_rows)
    write_csv(RESULTS / "recommendation_metrics.csv", rec_rows)
    write_csv(RESULTS / "latency.csv", lat_rows)
    (RESULTS / "latency_summary.json").write_text(json.dumps(summary, indent=2) + "\n", "utf-8")

    paths = get_paths()
    manifest = json.loads(paths.manifest_path.read_text("utf-8"))
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True,
                            text=True).stdout.splitlines()
    run_manifest = {
        "git_commit": commit,
        "created": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config_sha256": sha256(paths.config_dir / "runtime.yaml"),
        "registry_sha256": sha256(paths.config_dir / "registry.yaml"),
        "dataset_sha256": {k: v["sha256"] for k, v in manifest["dataset"]["files"].items()},
        "model": manifest.get("model", {}),
        "test_split_sha256": split_hash,
        "test_split_frozen": frozen is not None,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "cpu": platform.processor(),
        "quick": args.quick,
        "packages": freeze,
    }
    (RESULTS / "run_manifest.json").write_text(json.dumps(run_manifest, indent=2) + "\n", "utf-8")

    for r in rows:
        flag = "" if r["passed"] == "" else ("PASS" if r["passed"] else "FAIL")
        print(f"  {r['metric']:<24} {r['split']:<9} {r['value']!s:<10} n={r['n']:<4} {flag}")
    for k, v in summary.items():
        print(f"  {k:<40} {v:.3f}" if isinstance(v, float) else f"  {k:<40} {v}")
    print(f"wrote {', '.join(sorted(p.name for p in RESULTS.iterdir()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
