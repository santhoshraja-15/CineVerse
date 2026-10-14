"""CompiledQuery IR: models, lowering, validators V1–V5, canonical JSON, hash and versioning.

A contract module (LR-3): imports only the standard library and Pydantic at run time; the
semantic and registry types used by `lower` are imported for type checking only.
Spec: CineVerse_IR_and_Execution_Plan_Specification §2, §2.1; T01 review C3 (sort keys).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from cineverse.compiler.registry import DomainRegistry
    from cineverse.compiler.semantic import SemanticResult

IR_VERSION = "1.0"


class IRVersionError(ValueError):
    """An IR document has a different major version."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DiagnosticModel(_Frozen):
    code: str
    severity: Literal["ERROR", "WARNING", "INFO"]
    message: str
    span: tuple[int, int] | None = None
    hint: str | None = None


class Preference(_Frozen):
    kind: Literal["genre", "text"]
    value: str
    polarity: Literal[1, -1]


class Constraint(_Frozen):
    field: Literal["genre", "year", "rating", "votes", "runtime", "language"]
    op: Literal["HAS", "NOT_HAS", "<=", ">=", "<", ">"]
    value: str | int | float
    strictness: Literal["hard", "soft"]
    span: tuple[int, int]


class Channels(_Frozen):
    semantic: bool
    metadata: bool = True


class Ranking(_Frozen):
    fusion: Literal["rrf"] = "rrf"
    rrf_k: int = 60
    diversity: Literal["none", "mmr"] = "none"
    mmr_lambda: float = 0.7


class Output(_Frozen):
    limit: int = Field(10, ge=1, le=50)
    explain: bool = True


def _strip_spans(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_spans(v) for k, v in obj.items() if k != "span"}
    if isinstance(obj, list):
        return [_strip_spans(v) for v in obj]
    return obj


def canonical_json(data: Any) -> str:
    """IR Spec §2.1 canonical JSON."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class CompiledQuery(_Frozen):
    ir_version: Literal["1.0"] = "1.0"
    source: str
    semantic_text: str
    preferences: list[Preference]
    constraints: list[Constraint]
    channels: Channels
    ranking: Ranking = Ranking()
    output: Output = Output()
    diagnostics: list[DiagnosticModel] = []

    def to_json(self) -> str:
        return canonical_json(self.model_dump(mode="json"))

    def hash(self) -> str:
        """SHA-256 of canonical JSON without source, diagnostics and every span."""
        data = self.model_dump(mode="json")
        data.pop("source")
        data.pop("diagnostics")
        return hashlib.sha256(canonical_json(_strip_spans(data)).encode("utf-8")).hexdigest()

    @classmethod
    def from_json(cls, s: str) -> CompiledQuery:
        data = json.loads(s)
        version = str(data.get("ir_version", IR_VERSION))
        if version.split(".")[0] != IR_VERSION.split(".")[0]:
            raise IRVersionError(f"unsupported IR major version {version!r}")
        data["ir_version"] = IR_VERSION
        return cls.model_validate(data)


@dataclass(frozen=True, slots=True)
class Capabilities:
    """What the runtime can do; read by the registry, optimizer and executor (T01 C2)."""

    exact_search: bool
    semantic_available: bool
    mmr_available: bool = False


def format_constraint(c: Constraint) -> str:
    """Printed predicate form 'field OP value' (IR Spec §6)."""
    return f"{c.field} {c.op} {c.value}"


# --------------------------------------------------------------------------- canonical order

INT_FIELDS = ("year", "votes", "runtime")
FIELD_OPS: dict[str, tuple[str, ...]] = {
    "genre": ("HAS", "NOT_HAS"),
    "language": ("HAS",),
    "year": ("<=", ">=", "<", ">"),
    "rating": ("<=", ">=", "<", ">"),
    "votes": ("<=", ">=", "<", ">"),
    "runtime": ("<=", ">=", "<", ">"),
}


def pref_key(p: Preference) -> tuple[str, str, int]:
    return (p.kind, p.value, p.polarity)


def constraint_key(c: Constraint) -> tuple[str, str, str, str]:
    return (c.field, c.op, str(c.value), c.strictness)


# --------------------------------------------------------------------------- lowering


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(i for i in items if i))


def lower(sem: SemanticResult, registry: DomainRegistry) -> CompiledQuery:
    """Annotated AST to IR. Lists keep source order; pass O2 sorts them (IR Spec §2)."""
    from cineverse.compiler.ast import walk  # stdlib-only module

    prefs: list[Preference] = []
    constraints: list[Constraint] = []
    limit = registry.config.limit.default
    diversity = False
    texts: list[str] = []
    genres: list[str] = []
    nodes = [(clause.span, n) for clause in sem.ast.clauses for n in walk(clause)]
    for clause_span, node in nodes:
        for a in sem.annotations.get(node.node_id, []):
            if a.kind == "limit":
                limit = int(a.value)  # type: ignore[call-overload]
            elif a.kind == "diversity":
                diversity = diversity or a.applied
            elif not a.applied or a.kind == "ignored":
                continue
            elif a.kind == "pref":
                kind: Literal["genre", "text"] = "genre" if a.field == "genre" else "text"
                prefs.append(Preference(kind=kind, value=str(a.value), polarity=a.polarity or 1))
                if a.polarity == 1:
                    (genres if kind == "genre" else texts).append(str(a.value))
            else:
                constraints.append(
                    Constraint(
                        field=a.field,
                        op=a.op,
                        value=a.value,
                        strictness=a.strictness or "hard",
                        span=clause_span,
                    )
                )
                if a.field == "genre" and a.op == "HAS" and a.strictness == "hard":
                    genres.append(str(a.value))
    negative = {p.value.lower() for p in prefs if p.polarity == -1 and p.kind == "text"}
    negative |= {registry.display(p.value).lower() for p in prefs
                 if p.polarity == -1 and p.kind == "genre"}
    negative |= {registry.display(str(c.value)).lower() for c in constraints
                 if c.field == "genre" and c.op == "NOT_HAS"}
    phrases = [t.lower() for t in texts] + [registry.display(g).lower() for g in genres]
    semantic_text = " ".join(p for p in _dedupe(phrases) if p not in negative)  # never negative
    return CompiledQuery(
        source=sem.ast.source,
        semantic_text=semantic_text,
        preferences=prefs,
        constraints=constraints,
        channels=Channels(semantic=registry.caps.semantic_available),
        ranking=Ranking(diversity="mmr" if diversity and registry.caps.mmr_available else "none"),
        output=Output(limit=limit),
        diagnostics=[
            DiagnosticModel(code=d.code, severity=d.severity.value, message=d.message,
                            span=d.span, hint=d.hint)
            for d in sem.diagnostics
        ],
    )


# --------------------------------------------------------------------------- validators


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(phrase) and f" {phrase} " in f" {text} "


def validate(
    ir: CompiledQuery, registry: DomainRegistry, *, after_passes: bool = False
) -> list[str]:
    """V1–V5; returns error messages (empty = valid). V5 applies only after the IR passes."""
    errors: list[str] = []
    for c in ir.constraints:
        if not registry.available(c.field):
            errors.append(f"V1: field {c.field} is not available")
        if c.op not in FIELD_OPS[c.field]:
            errors.append(f"V2: op {c.op} not valid for {c.field}")
    hard_genres = {(c.op, c.value) for c in ir.constraints
                   if c.field == "genre" and c.strictness == "hard"}
    for op, g in sorted(hard_genres, key=str):
        if op == "HAS" and ("NOT_HAS", g) in hard_genres:
            errors.append(f"V3: {g} is both required and excluded")
    negatives = [p.value.lower() for p in ir.preferences if p.polarity == -1 and p.kind == "text"]
    negatives += [registry.display(p.value).lower() for p in ir.preferences
                  if p.polarity == -1 and p.kind == "genre"]
    negatives += [registry.display(str(c.value)).lower() for c in ir.constraints
                  if c.field == "genre" and c.op == "NOT_HAS"]
    for n in negatives:
        if _contains_phrase(ir.semantic_text, n):
            errors.append(f"V4: semantic_text contains negative term '{n}'")
    if after_passes:
        if ir.preferences != sorted(set(ir.preferences), key=pref_key):
            errors.append("V5: preferences not sorted and unique")
        keys = [constraint_key(c) for c in ir.constraints]
        if keys != sorted(set(keys)):
            errors.append("V5: constraints not sorted and unique")
        for c in ir.constraints:
            if c.field in INT_FIELDS and c.op in ("<", ">"):
                errors.append(f"V5: int field {c.field} uses {c.op}")
    return errors
