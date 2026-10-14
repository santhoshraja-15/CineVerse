"""Spec: IR and Execution Plan Specification §1; Flow Document F2; SRS FR-01, FR-05.3."""

from __future__ import annotations

from cineverse.compiler.driver import compile_text


def test_ok_request_produces_every_stage(registry, runtime_cfg):
    comp = compile_text("dark sci-fi after 2010, top 5", registry, runtime_cfg)
    assert comp.ok and comp.tokens and comp.ast and comp.semantic
    assert comp.ir_lowered and comp.ir and comp.plan_unoptimized and comp.plan and comp.program


def test_timings_for_each_stage(registry, runtime_cfg):
    comp = compile_text("comedy", registry, runtime_cfg)
    assert set(comp.timings_ms) == {"lex", "parse", "analyse", "lower", "passes", "plan",
                                    "optimize", "codegen"}
    assert all(v >= 0 for v in comp.timings_ms.values())


def test_error_stops_before_planning(registry, runtime_cfg):
    comp = compile_text("only horror and no horror", registry, runtime_cfg)
    assert not comp.ok and comp.ir is None and comp.plan is None and comp.program is None
    assert [d.code for d in comp.diagnostics] == ["S107"]


def test_s113_stops_at_lexing(registry, runtime_cfg):
    comp = compile_text("x" * 301, registry, runtime_cfg)
    assert not comp.ok and comp.ast is None and [d.code for d in comp.diagnostics] == ["S113"]


def test_warnings_copied_into_ir(registry, runtime_cfg):
    comp = compile_text("comedy under 2 hours", registry, runtime_cfg)
    assert comp.ok and [d.code for d in comp.ir.diagnostics] == ["S112", "S105"]


def test_lexer_and_parser_diagnostics_kept(registry, runtime_cfg):
    comp = compile_text("drama, stars ★", registry, runtime_cfg)
    assert comp.ok and [d.code for d in comp.diagnostics] == ["L001", "P001"]


def test_trace_parts_are_json_ready(registry, runtime_cfg):
    import json

    parts = compile_text("no romance", registry, runtime_cfg).to_trace_parts()
    json.dumps(parts)
    assert parts["program"][0] == "%s0 = SCAN"


def test_deterministic_ir_and_program(registry, runtime_cfg):
    a = compile_text("thoughtful sci-fi mystery after 2010", registry, runtime_cfg)
    b = compile_text("thoughtful sci-fi mystery after 2010", registry, runtime_cfg)
    assert a.ir.to_json() == b.ir.to_json() and a.printed_program() == b.printed_program()
