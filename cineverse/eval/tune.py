"""Grid search of β, λ, μ and C on the judged dev requests (objective: mean NDCG@10).

Reads only dev-split judgments; refuses to run without them (human task H2). Prints the grid and
the chosen values; it does not write runtime.yaml (the team freezes the values by decision).
Spec: CineVerse_Evaluation_and_Benchmarking_Plan §8 step 1; Claude Code Master Instructions T26.
"""

from __future__ import annotations

import argparse
import dataclasses
import itertools
import json
from pathlib import Path

from cineverse.eval.metrics import ndcg_at_k
from cineverse.eval.rec_eval import K, load_judgments

GRID = {"beta": (0.05, 0.1, 0.2), "lam": (0.1, 0.3, 0.5), "mu": (0.1, 0.2, 0.4),
        "candidate_budget": (100, 200, 400)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", default="dev", choices=["dev"])
    parser.add_argument("--benchmark", type=Path, default=Path("benchmark/requests.jsonl"))
    parser.add_argument("--judgments", type=Path, default=Path("benchmark/judgments.csv"))
    args = parser.parse_args(argv)

    items = [json.loads(line) for line in args.benchmark.read_text("utf-8").splitlines() if line]
    dev = [i for i in items if i["split"] == "dev" and i["baseline_spec"] is not None]
    judgments = {k: v for k, v in load_judgments(args.judgments).items()
                 if k in {i["id"] for i in dev}}
    judged = [i for i in dev if i["id"] in judgments]
    if not judged:
        print("No dev judgments found: tuning needs benchmark/judgments.csv rows for dev "
              "requests (human task H2). Nothing was tuned.")
        return 2

    from cineverse import default_runtime
    from cineverse.baseline.baseline import BaselineSpec, ranked_baseline

    ctx, _ = default_runtime()
    results = []
    for beta, lam, mu, c in itertools.product(*GRID.values()):
        cfg = dataclasses.replace(
            ctx.cfg, candidate_budget=c,
            soft=dataclasses.replace(ctx.cfg.soft, beta=beta, lam=lam, mu=mu))
        trial = dataclasses.replace(ctx, cfg=cfg)
        scores = []
        for item in judged:
            spec = BaselineSpec.from_dict(item["baseline_spec"])
            spec.limit = K
            scores.append(ndcg_at_k(list(ranked_baseline(spec, trial).ids), judgments[item["id"]]))
        results.append(((beta, lam, mu, c), sum(scores) / len(scores)))
        print(f"beta={beta:<5} lambda={lam:<4} mu={mu:<4} C={c:<4} NDCG@10={results[-1][1]:.4f}")
    best = max(results, key=lambda r: (r[1], -r[0][3]))
    beta, lam, mu, c = best[0]
    print(f"\nchosen on {len(judged)} dev requests: beta={beta} lambda={lam} mu={mu} C={c} "
          f"(NDCG@10 {best[1]:.4f}); record in the decision log, then freeze runtime.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
