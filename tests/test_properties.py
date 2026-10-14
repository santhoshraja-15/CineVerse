"""Property tests with seeded generators (no Hypothesis).

Spec: Optimizer and Equivalence Testing Specification §7; SRS NFR-04.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from cineverse.compiler import lexicon
from cineverse.compiler.codegen import generate
from cineverse.compiler.driver import compile_text
from cineverse.compiler.ir import Capabilities, Channels, CompiledQuery, Constraint, Preference
from cineverse.compiler.optimizer import optimize
from cineverse.compiler.passes import run_ir_passes
from cineverse.compiler.planner import build_plan
from cineverse.runtime.constraints import mask
from cineverse.runtime.context import RankedList, RuntimeContext
from cineverse.runtime.executor import execute
from cineverse.runtime.scoring import soft_score
from cineverse.runtime.semantic_index import NumpyIndex
from tests.stub_encoder import StubEncoder

ROOT = Path(__file__).resolve().parents[1]
GENRES = ["Comedy", "Drama", "Sci-Fi", "Romance", "Thriller", "Mystery", "Horror", "Crime"]


@pytest.fixture(scope="module")
def ctx(toy_catalog_module, runtime_cfg_module) -> RuntimeContext:
    enc = StubEncoder()
    texts = [str(t) for t in toy_catalog_module.column("embed_text")]
    index = NumpyIndex(enc.encode(texts), toy_catalog_module.all_ids(), enc)
    return RuntimeContext(toy_catalog_module, index, enc, runtime_cfg_module,
                          Capabilities(True, True))


def random_hard(rng: random.Random) -> list[Constraint]:
    preds = []
    for _ in range(rng.randint(0, 3)):
        kind = rng.choice(["year", "rating", "votes", "genre"])
        if kind == "genre":
            preds.append(Constraint(field="genre", op=rng.choice(["HAS", "NOT_HAS"]),
                                    value=rng.choice(GENRES), strictness="hard", span=(0, 0)))
        elif kind == "year":
            preds.append(Constraint(field="year", op=rng.choice([">=", "<="]),
                                    value=rng.randint(1960, 2020), strictness="hard", span=(0, 0)))
        elif kind == "rating":
            preds.append(Constraint(field="rating", op=rng.choice([">=", "<=", ">"]),
                                    value=rng.choice([3.0, 3.5, 3.9, 4.0]), strictness="hard",
                                    span=(0, 0)))
        else:
            preds.append(Constraint(field="votes", op=rng.choice([">=", "<="]),
                                    value=rng.choice([10, 50, 100]), strictness="hard",
                                    span=(0, 0)))
    return preds


def test_o4_pushdown_on_200_random_predicate_sets(ctx):
    """optimized == unoptimized for random hard predicates and descriptor text."""
    rng = random.Random(42)
    descriptors = sorted(lexicon.DESCRIPTORS)
    for trial in range(200):
        text = " ".join(rng.sample(descriptors, rng.randint(0, 2)))
        prefs = [Preference(kind="text", value=t, polarity=1) for t in text.split()]
        if rng.random() < 0.5:
            prefs.append(Preference(kind="genre", value=rng.choice(GENRES), polarity=1))
        ir = CompiledQuery(source="p", semantic_text=text, preferences=prefs,
                           constraints=random_hard(rng), channels=Channels(semantic=True))
        ir, _ = run_ir_passes(ir, {"O2", "O1"})
        plan = build_plan(ir, ctx.cfg)
        opt, _ = optimize(plan, ir, ctx.caps, {"O3", "O4"})
        a = execute(generate(plan), ctx, ir=ir).results
        b = execute(generate(opt), ctx, ir=ir).results
        assert [(r.movie_id, round(r.score, 6)) for r in a] == \
               [(r.movie_id, round(r.score, 6)) for r in b], f"trial {trial}: {ir.constraints}"


def test_o2_idempotence_on_random_bounds():
    rng = random.Random(42)
    for _ in range(200):
        cons = [Constraint(field=rng.choice(["year", "votes", "rating"]),
                           op=rng.choice(["<", ">", "<=", ">="]), value=rng.randint(1, 3000),
                           strictness=rng.choice(["hard", "soft"]), span=(0, 0))
                for _ in range(rng.randint(0, 4))]
        cons = [c.model_copy(update={"value": float(c.value)}) if c.field == "rating" else c
                for c in cons]
        ir = CompiledQuery(source="p", semantic_text="", preferences=[], constraints=cons,
                           channels=Channels(semantic=True))
        once, _ = run_ir_passes(ir, {"O2"})
        assert run_ir_passes(once, {"O2"})[0] == once


def test_o1_soundness_eligible_set_and_scores_unchanged(ctx):
    rng = random.Random(42)
    ids = ctx.catalog.all_ids()
    rl = RankedList(tuple(int(i) for i in ids), tuple(0.5 for _ in ids), "rrf", {})
    for _ in range(200):
        cons = [Constraint(field="year", op=rng.choice([">=", "<="]), value=rng.randint(1960, 2020),
                           strictness=rng.choice(["hard", "soft"]), span=(0, 0))
                for _ in range(rng.randint(1, 4))]
        ir = CompiledQuery(source="p", semantic_text="", preferences=[], constraints=cons,
                           channels=Channels(semantic=True))
        out, _ = run_ir_passes(ir, {"O1"})

        def eligible_and_scores(q):
            hard = [c for c in q.constraints if c.strictness == "hard"]
            soft = [c for c in q.constraints if c.strictness == "soft"]
            keep = set(mask(ctx.catalog, ids, hard).tolist())
            scored = soft_score(ctx.catalog, rl, [], soft, ctx.cfg.soft)
            return keep, {m: round(s, 6) for m, s in zip(scored.ids, scored.scores, strict=True)
                          if m in keep}

        assert eligible_and_scores(ir) == eligible_and_scores(out)


def test_determinism_byte_identical_ir_and_results(ctx, registry):
    items = [json.loads(line) for line in
             (ROOT / "benchmark" / "requests.jsonl").read_text("utf-8").splitlines() if line]
    for item in items:
        a = compile_text(item["text"], registry, ctx.cfg)
        b = compile_text(item["text"], registry, ctx.cfg)
        if not a.ok:
            assert [d.code for d in a.diagnostics] == [d.code for d in b.diagnostics]
            continue
        assert a.ir.to_json() == b.ir.to_json()
        ra = execute(a.program, ctx, ir=a.ir).results
        rb = execute(b.program, ctx, ir=b.ir).results
        assert [(r.movie_id, r.score, r.reasons) for r in ra] == \
               [(r.movie_id, r.score, r.reasons) for r in rb]
