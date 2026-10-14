"""Spec: IR and Execution Plan Specification §2, §2.1, §8."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from cineverse.compiler.ir import (
    Channels,
    CompiledQuery,
    Constraint,
    IRVersionError,
    Output,
    Preference,
    lower,
    validate,
)
from cineverse.compiler.lexer import lex
from cineverse.compiler.parser import parse
from cineverse.compiler.semantic import analyse

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = [
    e for e in json.loads(
        (ROOT / "docs" / "CineVerse_Example_Requests_and_Expected_Outputs.json").read_text("utf-8")
    )["examples"] if e["expected"]["ok"]
]


@pytest.fixture
def compile_ir(registry):
    def run(text: str) -> CompiledQuery:
        return lower(analyse(parse(lex(text, registry)[0], text)[0], registry), registry)

    return run


def C(field, op, value, strictness="hard", span=(0, 0)):
    return Constraint(field=field, op=op, value=value, strictness=strictness, span=span)


def P(kind, value, polarity):
    return Preference(kind=kind, value=value, polarity=polarity)


def q(**kw) -> CompiledQuery:
    base = dict(source="s", semantic_text="", preferences=[], constraints=[],
                channels=Channels(semantic=True))
    base.update(kw)
    return CompiledQuery(**base)


def canon_int(c: dict) -> str:
    """Compare before O2 exists: rewrite integer < and > the way O2 will."""
    c = {k: v for k, v in c.items() if k != "span"}
    if c["field"] in ("year", "votes", "runtime") and c["op"] in ("<", ">"):
        c["value"] += 1 if c["op"] == ">" else -1
        c["op"] += "="
    return json.dumps(c, sort_keys=True)


# --------------------------------------------------------------------------- lowering


@pytest.mark.parametrize("ex", [e for e in EXAMPLES if e["id"] != "EX25"],
                         ids=[e["id"] for e in EXAMPLES if e["id"] != "EX25"])
def test_lowering_matches_gold_ir_as_sets(ex, compile_ir):
    """Roadmap Step 7: lists compared as sets until O2 exists (EX25 needs O1)."""
    d, gold = compile_ir(ex["text"]).model_dump(mode="json"), ex["expected"]["ir"]
    assert d["semantic_text"] == gold["semantic_text"]
    assert sorted(map(json.dumps, d["preferences"])) == sorted(map(json.dumps, gold["preferences"]))
    assert sorted({canon_int(c) for c in d["constraints"]}) == sorted(
        json.dumps(c, sort_keys=True) for c in gold["constraints"])
    for key in ("channels", "ranking", "output"):
        assert d[key] == gold[key]
    assert [x["code"] for x in d["diagnostics"]] == gold["diagnostics"]


def test_semantic_text_order_and_no_negatives(compile_ir, registry):
    ir = compile_ir("dark comedy, no horror, little romance, not too violent, twist")
    assert ir.semantic_text == "dark twist comedy"
    assert validate(ir, registry) == []


def test_hard_has_genres_join_semantic_text(compile_ir):
    assert compile_ir("only animated comedies").semantic_text == "animation comedy"


def test_constraint_span_is_clause_span(compile_ir):
    (c,) = compile_ir("thoughtful sci-fi mystery after 2010").constraints
    assert c.span == (26, 36)


def test_between_lowers_to_two_bounds(compile_ir):
    ops = [(c.op, c.value) for c in compile_ir("between 2000 and 2010").constraints]
    assert ops == [(">=", 2000), ("<=", 2010)]


def test_unapplied_annotations_not_lowered(compile_ir):
    assert compile_ir("comedy under 2 hours").constraints == []


def test_rating_value_is_float_and_year_int(compile_ir):
    ir = compile_ir("after 2015, rated at least 4")
    assert {c.field: type(c.value) for c in ir.constraints} == {"year": int, "rating": float}


def test_channels_follow_registry_capability(registry, compile_ir):
    assert compile_ir("comedy").channels.semantic is registry.caps.semantic_available


# --------------------------------------------------------------------------- validators


def test_v1_unavailable_field(registry):
    assert validate(q(constraints=[C("runtime", "<=", 120)]), registry)[0].startswith("V1")


def test_v2_invalid_op(registry):
    assert validate(q(constraints=[C("genre", ">=", "Comedy")]), registry)[0].startswith("V2")


def test_v3_genre_both_has_and_not_has(registry):
    ir = q(constraints=[C("genre", "HAS", "Horror"), C("genre", "NOT_HAS", "Horror")])
    assert any(e.startswith("V3") for e in validate(ir, registry))


def test_v4_negative_term_in_semantic_text(registry):
    ir = q(semantic_text="gore comedy", preferences=[P("text", "gore", -1)])
    assert validate(ir, registry) == ["V4: semantic_text contains negative term 'gore'"]


def test_v5_unsorted_and_strict_int_ops(registry):
    ir = q(preferences=[P("text", "b", 1), P("genre", "Comedy", 1)],
           constraints=[C("year", ">", 2000)])
    errors = validate(ir, registry, after_passes=True)
    assert "V5: preferences not sorted and unique" in errors
    assert "V5: int field year uses >" in errors
    assert validate(ir, registry) == []  # V5 only after passes


def test_v5_float_strict_op_allowed(registry):
    assert validate(q(constraints=[C("rating", ">", 4.0)]), registry, after_passes=True) == []


# --------------------------------------------------------------------------- serialisation


def test_round_trip_every_example(compile_ir):
    for ex in EXAMPLES:
        ir = compile_ir(ex["text"])
        assert CompiledQuery.from_json(ir.to_json()) == ir


def test_canonical_json_sorted_and_compact():
    text = q(semantic_text="x").to_json()
    assert text.startswith('{"channels":') and ", " not in text and ": " not in text


def test_hash_ignores_source_spans_and_diagnostics():
    a = q(source="one", constraints=[C("year", ">=", 2011, span=(0, 5))])
    b = q(source="two", constraints=[C("year", ">=", 2011, span=(9, 20))],
          diagnostics=[{"code": "S112", "severity": "INFO", "message": "m"}])
    assert a.hash() == b.hash()
    assert a.hash() != q(constraints=[C("year", ">=", 2012)]).hash()


def test_from_json_accepts_same_major_and_defaults_missing_optional():
    data = json.loads(q().to_json())
    data["ir_version"] = "1.3"
    del data["output"]
    ir = CompiledQuery.from_json(json.dumps(data))
    assert ir.ir_version == "1.0" and ir.output == Output()


def test_from_json_rejects_other_major():
    data = json.loads(q().to_json())
    data["ir_version"] = "2.0"
    with pytest.raises(IRVersionError):
        CompiledQuery.from_json(json.dumps(data))


def test_models_are_frozen():
    ir = q()
    with pytest.raises(ValidationError):
        ir.semantic_text = "changed"  # type: ignore[misc]


def test_limit_bounds_enforced():
    with pytest.raises(ValidationError):
        Output(limit=51)
