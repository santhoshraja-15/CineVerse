"""Semantic analysis: rules S1–S13 over the AST, producing annotations and diagnostics.

Annotation kinds: "pref" (soft genre/text preference), "constraint" (hard genre or any numeric
bound, hard or soft), "limit", "diversity", "ignored". Diagnostics are ordered by rule, then span.
Spec: CineVerse_Compiler_Frontend_Specification §6; T01 review C6 (S101 vocabulary).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal

from cineverse.compiler import lexicon
from cineverse.compiler.ast import (
    ConstraintClause,
    DescriptorTerm,
    DiversityClause,
    ExclusionClause,
    GenreTerm,
    LimitClause,
    NumberNode,
    PreferenceClause,
    RequestNode,
    Span,
)
from cineverse.compiler.diagnostics import Diagnostic, make
from cineverse.compiler.registry import DomainRegistry

INT_FIELDS = ("year", "votes", "runtime")
S101_MIN_WORD, S101_MIN_VOCAB, S101_MAX_DISTANCE = 4, 5, 2


@dataclass
class Annotation:
    kind: Literal["pref", "constraint", "limit", "diversity", "ignored"]
    field: str | None  # genre/year/rating/votes/runtime/language/text
    op: str | None  # HAS, NOT_HAS, <, <=, >, >=
    value: object  # canonical value(s) after conversion
    polarity: Literal[1, -1] | None
    strictness: Literal["hard", "soft"] | None
    applied: bool  # False when S105 (or S110) drops it


@dataclass
class SemanticResult:
    ast: RequestNode
    annotations: dict[int, list[Annotation]]  # node_id -> annotations
    diagnostics: list[Diagnostic]


@dataclass
class _State:
    registry: DomainRegistry
    source: str
    annotations: dict[int, list[Annotation]] = field(default_factory=dict)
    spans: dict[int, Span] = field(default_factory=dict)
    diags: list[tuple[int, Diagnostic]] = field(default_factory=list)

    def add(self, node_id: int, ann: Annotation, clause_span: Span) -> None:
        self.annotations.setdefault(node_id, []).append(ann)
        self.spans[node_id] = clause_span

    def emit(self, rule: int, code: str, span: Span | None, hint: str | None = None,
             **fields: Any) -> None:
        self.diags.append((rule, make(code, span=span, hint=hint, **fields)))

    def text(self, span: Span) -> str:
        return self.source[span[0]:span[1]]

    def all(self) -> list[tuple[Annotation, Span]]:
        return [(a, self.spans[n]) for n, anns in self.annotations.items() for a in anns]


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def looks_like_genre(word: str, registry: DomainRegistry) -> str | None:
    """S1/S101: canonical genre within edit distance 2 of `word` (T01 C6), else None."""
    if len(word) < S101_MIN_WORD:
        return None
    best: tuple[int, str] | None = None
    for phrase, genres in registry.genre_lexemes.items():
        if len(phrase) < S101_MIN_VOCAB:
            continue
        d = edit_distance(word, phrase)
        if d <= S101_MAX_DISTANCE and (best is None or d < best[0]):
            best = (d, genres[0])
    return best[1] if best else None


def _fmt(v: float) -> str:
    return f"{v:g}"


# ------------------------------------------------------------------ terms (S1, S7, S8, S13)


def _term_descriptor(st: _State, term: DescriptorTerm) -> None:
    """S1: a WORD that is not a descriptor but looks like a genre gets S101."""
    if term.text in lexicon.DESCRIPTORS:
        return
    genre = looks_like_genre(term.text, st.registry)
    if genre is not None:
        st.emit(1, "S101", term.span, hint=f"Did you mean {genre}?", word=term.text)


def _preference(st: _State, c: PreferenceClause) -> None:
    strict_or = c.modifier == "STRICT" and c.has_or
    if strict_or:
        st.emit(13, "S114", c.span)
    for t in c.terms:
        if isinstance(t, GenreTerm):
            for g in t.genres:
                if c.modifier == "STRICT" and not strict_or:
                    st.add(t.node_id, Annotation("constraint", "genre", "HAS", g, None, "hard",
                                                 True), c.span)
                else:
                    st.add(t.node_id, Annotation("pref", "genre", None, g, 1, "soft", True), c.span)
        else:
            _term_descriptor(st, t)
            if c.modifier == "STRICT":
                st.emit(7, "S106", t.span, text=t.text)
            st.add(t.node_id, Annotation("pref", "text", None, t.text, 1, "soft", True), c.span)


def _exclusion(st: _State, c: ExclusionClause) -> None:
    hard = c.strength == "HARD" and not c.hedged
    for t in c.targets:
        if isinstance(t, GenreTerm):
            for g in t.genres:
                if hard:
                    st.add(t.node_id, Annotation("constraint", "genre", "NOT_HAS", g, None, "hard",
                                                 True), c.span)
                else:
                    st.add(t.node_id, Annotation("pref", "genre", None, g, -1, "soft", True),
                           c.span)
        else:
            _term_descriptor(st, t)
            if hard:  # S8: no field to check a descriptor exclusion
                st.emit(8, "S106", c.span, text=t.text)
            st.add(t.node_id, Annotation("pref", "text", None, t.text, -1, "soft", True), c.span)


# --------------------------------------------------------------------------- constraints (S2–S7)


def _unit_of(c: ConstraintClause) -> str | None:
    units = [v.unit_raw for v in c.values if v.unit_raw] + ([c.unit_raw] if c.unit_raw else [])
    return units[0] if units else None


def _infer_field(st: _State, c: ConstraintClause) -> str | None:
    """S2: FIELD word, else unit, else decade or an integer in the year domain."""
    if c.field_raw is not None:
        return lexicon.FIELD[c.field_raw]
    unit = _unit_of(c)
    if unit is not None:
        return st.registry.config.units[unit].field
    if c.op == "DECADE":
        return "year"
    lo, hi = st.registry.year_domain
    if all(isinstance(v.value, int) and lo <= v.value <= hi for v in c.values):
        return "year"
    return None


def _bounds(c: ConstraintClause) -> list[tuple[str, NumberNode]]:
    if c.op in ("BETWEEN", "DECADE"):
        return [(">=", c.values[0]), ("<=", c.values[1])]
    return [(c.op, c.values[0])]


def _constraint(st: _State, c: ConstraintClause) -> None:
    reg = st.registry
    name = _infer_field(st, c)
    if name is None:
        st.emit(2, "S102", c.span, text=st.text(c.span))
        return
    spec = reg.field(name)
    assert spec is not None
    numeric = spec.type in ("int", "float")
    if not numeric:  # S3: comparisons on genre/language
        shown = c.op if c.op not in ("BETWEEN", "DECADE") else ">="
        st.emit(3, "S103", c.span, op=shown, field=name)
        return

    unit = _unit_of(c)
    factor = reg.config.units[unit].factor if unit and unit in reg.config.units else 1
    strictness: Literal["hard", "soft"] = "soft" if c.hedged else "hard"
    lo, hi = reg.domain(name)
    anns: list[Annotation] = []
    for op, num in _bounds(c):
        mapped = {"<": "<=", ">": ">="}.get(op, op)
        if mapped not in spec.ops:
            st.emit(3, "S103", c.span, op=op, field=name)
            return
        value: float = num.value * factor
        if spec.type == "int":
            if float(value) != int(value):
                st.emit(3, "S103", c.span, op=op, field=name)
                return
            value = int(value)
        else:
            value = float(value)
        if (lo is not None and value < lo) or (hi is not None and value > hi):  # S4
            show = str if spec.type == "float" else _fmt
            st.emit(4, "S104", c.span, value=_fmt(value), field=name,
                    lo=show(lo) if lo is not None else "", hi=show(hi) if hi is not None else "∞")
            return
        anns.append(Annotation("constraint", name, op, value, None, strictness, True))

    if factor != 1:  # S5
        unit_name = spec.unit or name
        original = ", ".join(f"{_fmt(v.value)} {unit}" for v in c.values)
        converted = ", ".join(f"{_fmt(a.value)} {unit_name}" for a in anns)  # type: ignore[arg-type]
        st.emit(5, "S112", c.span, **{"from": original, "to": converted})
    if not spec.available:  # S6
        st.emit(6, "S105", c.span, field=name, text=st.text(c.span))
        anns = [replace(a, applied=False) for a in anns]
    for a in anns:
        st.add(c.node_id, a, c.span)


# --------------------------------------------------------------------------- whole-request rules


def _contradictions(st: _State) -> None:
    """S9: same genre hard HAS and hard NOT_HAS."""
    hard = [(a, sp) for a, sp in st.all()
            if a.applied and a.field == "genre" and a.strictness == "hard"]
    has = {a.value: sp for a, sp in hard if a.op == "HAS"}
    for a, sp in hard:
        if a.op == "NOT_HAS" and a.value in has:
            other = has[a.value]
            span = (min(sp[0], other[0]), max(sp[1], other[1]))
            st.emit(9, "S107", span, genre=a.value)


def _empty_ranges(st: _State) -> None:
    """S10: hard bounds on one field with an empty intersection."""
    by_field: dict[str, list[tuple[Annotation, Span]]] = {}
    for a, sp in st.all():
        if a.applied and a.kind == "constraint" and a.strictness == "hard" and a.field != "genre":
            by_field.setdefault(str(a.field), []).append((a, sp))
    for name, items in sorted(by_field.items()):
        lo, lo_strict, hi, hi_strict = float("-inf"), False, float("inf"), False
        for a, _ in items:
            v = float(a.value)  # type: ignore[arg-type]
            if name in INT_FIELDS and a.op in ("<", ">"):
                v, op = (v + 1, ">=") if a.op == ">" else (v - 1, "<=")
            else:
                op = str(a.op)
            if op in (">", ">=") and (v > lo or (v == lo and op == ">")):
                lo, lo_strict = v, op == ">"
            if op in ("<", "<=") and (v < hi or (v == hi and op == "<")):
                hi, hi_strict = v, op == "<"
        if lo > hi or (lo == hi and (lo_strict or hi_strict)):
            span = (min(sp[0] for _, sp in items), max(sp[1] for _, sp in items))
            st.emit(10, "S108", span, field=name)


def _precedence(st: _State) -> None:
    """S11: a hard genre condition overrides an opposite soft genre preference."""
    hard = {(a.op, a.value) for a, _ in st.all()
            if a.applied and a.field == "genre" and a.strictness == "hard"}
    for node_id, anns in st.annotations.items():
        for i, a in enumerate(anns):
            if a.kind != "pref" or a.field != "genre" or not a.applied:
                continue
            if (a.polarity == 1 and ("NOT_HAS", a.value) in hard) or (
                a.polarity == -1 and ("HAS", a.value) in hard
            ):
                anns[i] = replace(a, applied=False)
                st.emit(11, "S110", st.spans[node_id], genre=a.value)


def analyse(ast: RequestNode, registry: DomainRegistry) -> SemanticResult:
    """Apply S1–S13; pure function of the AST and registry."""
    st = _State(registry, ast.source)
    for c in ast.clauses:
        if isinstance(c, PreferenceClause):
            _preference(st, c)
        elif isinstance(c, ExclusionClause):
            _exclusion(st, c)
        elif isinstance(c, ConstraintClause):
            _constraint(st, c)
        elif isinstance(c, LimitClause):
            lim = registry.config.limit
            n = lim.default if c.n is None else c.n
            if not lim.min <= n <= lim.max:  # S4
                n = min(max(n, lim.min), lim.max)
                st.emit(4, "S109", c.span, n=n)
            st.add(c.node_id, Annotation("limit", None, None, n, None, None, True), c.span)
        elif isinstance(c, DiversityClause):
            available = registry.caps.mmr_available
            if not available:  # S6
                st.emit(6, "S105", c.span, field="diversity", text=st.text(c.span))
            st.add(c.node_id, Annotation("diversity", None, None, None, None, None, available),
                   c.span)
        else:
            st.add(c.node_id, Annotation("ignored", None, None, c.text, None, None, False), c.span)

    _contradictions(st)
    _empty_ranges(st)
    _precedence(st)
    already_failed = any(d.severity.value == "ERROR" for _, d in st.diags)
    nothing = not any(a.applied and a.kind in ("pref", "constraint") for a, _ in st.all())
    if nothing and not already_failed:  # S12 (not repeated after an earlier ERROR)
        st.emit(12, "S111", None)

    ordered = sorted(st.diags, key=lambda rd: (rd[0], rd[1].span or (-1, -1)))
    return SemanticResult(ast, st.annotations, [d for _, d in ordered])
