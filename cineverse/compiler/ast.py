"""AST node classes (frozen) and to_dict for golden files and the UI.

Spec: CineVerse_Compiler_Frontend_Specification §5.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Literal

Span = tuple[int, int]


@dataclass(frozen=True, slots=True)
class GenreTerm:
    raw: str
    genres: tuple[str, ...]
    span: Span
    node_id: int


@dataclass(frozen=True, slots=True)
class DescriptorTerm:
    text: str
    span: Span
    node_id: int


Term = GenreTerm | DescriptorTerm


@dataclass(frozen=True, slots=True)
class NumberNode:
    value: int | float
    unit_raw: str | None
    span: Span
    node_id: int


@dataclass(frozen=True, slots=True)
class PreferenceClause:
    terms: tuple[Term, ...]
    modifier: Literal["NONE", "HEDGE", "STRICT"]
    has_or: bool
    span: Span
    node_id: int


@dataclass(frozen=True, slots=True)
class ExclusionClause:
    targets: tuple[Term, ...]
    strength: Literal["HARD", "SOFT"]
    hedged: bool
    span: Span
    node_id: int


@dataclass(frozen=True, slots=True)
class ConstraintClause:
    field_raw: str | None
    op: Literal["<", "<=", ">", ">=", "BETWEEN", "DECADE"]
    values: tuple[NumberNode, ...]
    unit_raw: str | None
    hedged: bool
    span: Span
    node_id: int


@dataclass(frozen=True, slots=True)
class LimitClause:
    n: int | None
    span: Span
    node_id: int


@dataclass(frozen=True, slots=True)
class DiversityClause:
    span: Span
    node_id: int


@dataclass(frozen=True, slots=True)
class ErrorNode:
    text: str
    span: Span
    node_id: int


Clause = (
    PreferenceClause
    | ExclusionClause
    | ConstraintClause
    | LimitClause
    | DiversityClause
    | ErrorNode
)


@dataclass(frozen=True, slots=True)
class RequestNode:
    clauses: tuple[Clause, ...]
    source: str
    span: Span
    node_id: int


Node = RequestNode | Clause | Term | NumberNode


def to_dict(node: Any) -> Any:
    """{"kind": ClassName, field: value, ...}; tuples become lists, spans [s, e]."""
    if isinstance(node, tuple):
        return [to_dict(n) for n in node]
    if hasattr(node, "__dataclass_fields__"):
        out: dict[str, Any] = {"kind": type(node).__name__}
        for f in fields(node):
            out[f.name] = to_dict(getattr(node, f.name))
        return out
    return node


def walk(node: Any) -> list[Any]:
    """All nodes in pre-order."""
    out = [node]
    if hasattr(node, "__dataclass_fields__"):
        for f in fields(node):
            value = getattr(node, f.name)
            if isinstance(value, tuple):
                for child in value:
                    if hasattr(child, "__dataclass_fields__"):
                        out += walk(child)
    return out
