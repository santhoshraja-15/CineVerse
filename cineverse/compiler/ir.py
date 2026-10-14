"""CompiledQuery IR: models, canonical JSON, hash and versioning.

Lowering and validators V1–V5 are added in task T16.
Spec: CineVerse_IR_and_Execution_Plan_Specification §2, §2.1.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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
