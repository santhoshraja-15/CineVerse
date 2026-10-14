"""IR passes, run in order O2 then O1; each application is logged.

O2 canonicalises integer comparisons (x > a -> x >= a+1, x < b -> x <= b-1) and sorts and
de-duplicates the lists. O1 removes duplicates, keeps the tighter of two hard bounds in one
direction, and drops a soft bound implied by a hard one. Two soft bounds are never merged.
Spec: CineVerse_Optimizer_and_Equivalence_Testing_Specification §1–§3, §8.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from cineverse.compiler.ir import (
    INT_FIELDS,
    CompiledQuery,
    Constraint,
    constraint_key,
    format_constraint,
    pref_key,
)


@dataclass
class RuleApplication:
    rule: Literal["O1", "O2", "O3", "O4"]
    level: Literal["ir", "plan"]
    detail: str
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)

    def display(self) -> str:
        """The form listed in the Example JSON `rules_fired`."""
        return f"{self.rule}: {self.detail}"

    def to_dict(self) -> dict[str, Any]:
        return {"rule": self.rule, "level": self.level, "detail": self.detail,
                "before": self.before, "after": self.after}


RuleLog = list[RuleApplication]


@dataclass(frozen=True)
class Rule:
    id: Literal["O1", "O2", "O3", "O4"]
    level: Literal["ir", "plan"]
    precondition: Callable[..., bool]
    apply: Callable[..., Any]


def _label(c: Constraint) -> str:
    return format_constraint(c) + (" (soft)" if c.strictness == "soft" else "")


# --------------------------------------------------------------------------- O2


def _o2_pre(ir: CompiledQuery) -> bool:
    return True  # sorting and de-duplication always apply


def _o2_apply(ir: CompiledQuery) -> tuple[CompiledQuery, str]:
    rewrites: list[str] = []
    cons: list[Constraint] = []
    for c in ir.constraints:
        if c.field in INT_FIELDS and c.op in (">", "<"):
            value = int(c.value) + (1 if c.op == ">" else -1)
            new = c.model_copy(update={"op": c.op + "=", "value": value})
            rewrites.append(f"{format_constraint(c)} -> {format_constraint(new)}"
                            + (" (soft)" if c.strictness == "soft" else ""))
            c = new
        cons.append(c)
    unique: dict[tuple[str, str, str, str], Constraint] = {}
    for c in cons:
        unique.setdefault(constraint_key(c), c)
    new_ir = ir.model_copy(update={
        "preferences": sorted(dict.fromkeys(ir.preferences), key=pref_key),
        "constraints": [unique[k] for k in sorted(unique)],
    })
    return new_ir, "; ".join(rewrites)


O2 = Rule("O2", "ir", _o2_pre, _o2_apply)


ALL_IR_RULES = (O2,)  # O1 is added in T23


def run_ir_passes(ir: CompiledQuery, enabled: set[str]) -> tuple[CompiledQuery, RuleLog]:
    """Run O2 then O1 (each once, if enabled and its precondition holds)."""
    log: RuleLog = []
    for rule in ALL_IR_RULES:
        if rule.id not in enabled or not rule.precondition(ir):
            continue
        before = ir.model_dump(mode="json")
        ir, detail = rule.apply(ir)
        if detail:
            log.append(RuleApplication(rule.id, "ir", detail, before, ir.model_dump(mode="json")))
    return ir, log
