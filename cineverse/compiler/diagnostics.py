"""Diagnostic codes, severities and message templates; diagnostics are values, not exceptions.

Spec: CineVerse_Compiler_Frontend_Specification §7.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Severity(Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    severity: Severity
    message: str
    span: tuple[int, int] | None
    hint: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "span": list(self.span) if self.span is not None else None,
            "hint": self.hint,
        }


TEMPLATES: dict[str, tuple[Severity, str]] = {
    "L001": (Severity.INFO, "Ignored character '{ch}'"),
    "P001": (Severity.WARNING, "Could not understand '{text}'; skipped"),
    "P002": (Severity.WARNING, "Number {n} has no meaning here"),
    "S101": (Severity.INFO, "'{word}' is not a known genre; used as a description"),
    "S102": (
        Severity.ERROR,
        "Cannot tell what '{text}' refers to (year, rating, votes or runtime?)",
    ),
    "S103": (Severity.ERROR, "'{op}' cannot be used with {field}"),
    "S104": (Severity.ERROR, "{value} is outside the range of {field} ({lo}–{hi})"),
    "S105": (
        Severity.WARNING,
        "{field} is not available in this catalogue; '{text}' was not applied",
    ),
    "S106": (Severity.WARNING, "'{text}' cannot be checked exactly; applied as a preference"),
    "S107": (Severity.ERROR, "{genre} is both required and excluded"),
    "S108": (Severity.ERROR, "No {field} satisfies all conditions"),
    "S109": (Severity.WARNING, "Number of results limited to {n}"),
    "S110": (Severity.WARNING, "Preference for {genre} overridden by a strict condition"),
    "S111": (Severity.ERROR, "Nothing to recommend from; add a genre, mood or condition"),
    "S112": (Severity.INFO, "Converted {from} to {to}"),
    "S113": (Severity.ERROR, "Request is empty or longer than {max} characters"),
    "S114": (Severity.WARNING, "'only … or …' cannot be applied strictly; used as preferences"),
    "X201": (Severity.WARNING, "Semantic search unavailable; results use metadata only"),
    "X202": (Severity.INFO, "No movie satisfies all strict conditions"),
}


def make(
    code: str,
    span: tuple[int, int] | None = None,
    hint: str | None = None,
    **fields: Any,
) -> Diagnostic:
    """Build a diagnostic from its template; every message comes from TEMPLATES."""
    severity, template = TEMPLATES[code]
    return Diagnostic(code, severity, template.format(**fields), span, hint)


def has_error(diagnostics: list[Diagnostic]) -> bool:
    return any(d.severity is Severity.ERROR for d in diagnostics)
