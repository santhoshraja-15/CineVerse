"""Every entry of the Example JSON: tokens, diagnostics, IR (no spans), rules fired, both
programs, IR hash equalities, and (on the real catalogue) executable result properties.

Spec: Claude Code Master Instructions T27; Example Requests and Expected Outputs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cineverse.compiler.driver import compile_text
from cineverse.runtime.executor import execute

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = json.loads(
    (ROOT / "docs" / "CineVerse_Example_Requests_and_Expected_Outputs.json").read_text("utf-8")
)["examples"]
IDS = [e["id"] for e in EXAMPLES]


def ir_without_spans(comp) -> dict:
    ir = json.loads(comp.ir.to_json())
    for c in ir["constraints"]:
        c.pop("span")
    ir["diagnostics"] = [d["code"] for d in ir["diagnostics"]]
    return ir


@pytest.mark.parametrize("ex", EXAMPLES, ids=IDS)
def test_example_compiles_exactly(ex, registry, runtime_cfg):
    exp = ex["expected"]
    opt = compile_text(ex["text"], registry, runtime_cfg, optimize=True)
    plain = compile_text(ex["text"], registry, runtime_cfg, optimize=False)
    assert [t.display() for t in opt.tokens] == exp["tokens"]
    assert [d.code for d in opt.diagnostics] == exp["diagnostics"]
    assert opt.ok is exp["ok"]
    if not exp["ok"]:
        assert opt.ir is None and opt.program is None
        return
    assert ir_without_spans(opt) == exp["ir"]
    assert [r.display() for r in opt.rule_log] == exp["rules_fired"]
    assert plain.printed_program() == exp["program_unoptimized"]
    assert opt.printed_program() == exp["program_optimized"]


def test_ir_hash_equal_only_for_paraphrases(registry, runtime_cfg):
    hashes = {e["id"]: compile_text(e["text"], registry, runtime_cfg).ir.hash()
              for e in EXAMPLES if e["expected"]["ok"]}
    assert hashes["EX23"] == hashes["EX24"]
    others = [h for k, h in hashes.items() if k not in ("EX23", "EX24")]
    assert len(set(others)) == len(others) and hashes["EX23"] not in others


# --------------------------------------------------------------------------- result properties


def _rec(ctx, r):
    return ctx.catalog.get(r.movie_id)


def years(ctx, results):
    return [_rec(ctx, r).year for r in results]


PROPERTIES = {
    "EX01": lambda ctx, res: len(res) == 5 and all(y is not None and y >= 2011
                                                   for y in years(ctx, res))
    and all("Romance" not in r.genres or ["genre", "Romance", "Romance"]
            in r.evidence["soft"]["neg_matches"] for r in res),
    "EX02": lambda ctx, res: len(res) == 10 and all("Musical" not in r.genres for r in res)
    and sum({"Animation", "Comedy"} & set(r.genres) != set() for r in res) > 5,
    "EX03": lambda ctx, res: len(res) == 10 and all("Romance" not in r.genres for r in res)
    and [r.evidence["popularity_rank"] for r in res] == list(range(1, 11)),
    "EX04": lambda ctx, res: all("Comedy" in r.genres and 1990 <= r.year <= 1999 for r in res),
    "EX05": lambda ctx, res: all(2000 <= r.year <= 2010 and _rec(ctx, r).rating is not None
                                 and _rec(ctx, r).rating >= 4.0 for r in res),
    "EX06": lambda ctx, res: all(r.year is None or r.year >= 2001 or
                                 r.evidence["soft"]["violated"] for r in res),
    "EX07": lambda ctx, res: len(res) == 10,
    "EX12": lambda ctx, res: len(res) == 10 and all(
        any("gore" in t for t in _rec(ctx, r).tags) == bool(r.evidence["soft"]["neg_matches"])
        for r in res),
    "EX13": lambda ctx, res: len(res) == 3,
    "EX14": lambda ctx, res: all(_rec(ctx, r).votes >= 100 for r in res),
    "EX15": lambda ctx, res: len(res) == 10,
    "EX16": lambda ctx, res: len(res) == 10,
    "EX17": lambda ctx, res: len(res) == 10,
    "EX18": lambda ctx, res: len(res) == 10,
    "EX19": lambda ctx, res: len(res) == 50,
    "EX20": lambda ctx, res: len(res) == 10,
    "EX21": lambda ctx, res: all(y is not None and y >= 2005 for y in years(ctx, res)),
    "EX22": lambda ctx, res: all(r.year >= 2016 and _rec(ctx, r).rating >= 4.0 for r in res)
    and [r.evidence["popularity_rank"] for r in res] == list(range(1, len(res) + 1)),
    "EX23": lambda ctx, res: all(y is not None and y >= 2011 for y in years(ctx, res)),
    "EX24": lambda ctx, res: all(y is not None and y >= 2011 for y in years(ctx, res)),
    "EX25": lambda ctx, res: all(y is not None and y >= 2011 for y in years(ctx, res)),
}
VALID = [e for e in EXAMPLES if e["expected"]["ok"]]


@pytest.mark.full
@pytest.mark.parametrize("ex", VALID, ids=[e["id"] for e in VALID])
def test_result_properties_on_real_catalogue(ex, full_ctx):
    ctx, registry = full_ctx
    comp = compile_text(ex["text"], registry, ctx.cfg)
    results = execute(comp.program, ctx, ir=comp.ir).results
    assert results, f"{ex['id']} returned nothing"
    assert PROPERTIES[ex["id"]](ctx, results), ex["expected"]["result_properties"]


@pytest.mark.full
def test_paraphrases_return_identical_results(full_ctx):
    ctx, registry = full_ctx
    out = []
    for text in ("comedies made after 2010", "comedy from 2011"):
        comp = compile_text(text, registry, ctx.cfg)
        out.append([(r.movie_id, r.score) for r in execute(comp.program, ctx, ir=comp.ir).results])
    assert out[0] == out[1]
