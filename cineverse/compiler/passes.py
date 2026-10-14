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

LOWER, UPPER = (">=", ">"), ("<=", "<")


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


# --------------------------------------------------------------------------- O1


def _tighter(a: Constraint, b: Constraint) -> Constraint:
    """The stronger of two bounds in the same direction."""
    if a.op in LOWER:
        return a if (a.value, a.op == ">") >= (b.value, b.op == ">") else b
    return a if (-float(a.value), a.op == "<") >= (-float(b.value), b.op == "<") else b


def _implies(hard: Constraint, soft: Constraint) -> bool:
    """Does the hard bound imply the soft bound (same field and direction)?"""
    h, s = float(hard.value), float(soft.value)
    if hard.op in LOWER:
        return h > s or (h == s and not (soft.op == ">" and hard.op == ">="))
    return h < s or (h == s and not (soft.op == "<" and hard.op == "<="))


def _direction(c: Constraint) -> str | None:
    return "lower" if c.op in LOWER else "upper" if c.op in UPPER else None


def _o1_pre(ir: CompiledQuery) -> bool:
    return True


def _o1_apply(ir: CompiledQuery) -> tuple[CompiledQuery, str]:
    details: list[str] = []
    seen: set[tuple[str, str, str, str]] = set()
    cons: list[Constraint] = []
    for c in ir.constraints:  # (a) duplicates
        key = constraint_key(c)
        if key in seen:
            details.append(f"removed duplicate {_label(c)}")
        else:
            seen.add(key)
            cons.append(c)

    drop: set[int] = set()
    for i, a in enumerate(cons):  # (b) two hard bounds, one field and direction
        for j in range(i + 1, len(cons)):
            b = cons[j]
            if i in drop or j in drop or a.strictness != "hard" or b.strictness != "hard":
                continue
            if a.field != b.field or _direction(a) is None or _direction(a) != _direction(b):
                continue
            keep = _tighter(a, b)
            loser = j if keep is a else i
            drop.add(loser)
            details.append(f"hard {format_constraint(cons[loser])} subsumed by hard "
                           f"{format_constraint(keep)}")
    for i, s in enumerate(cons):  # (c) soft bound implied by a hard bound
        if i in drop or s.strictness != "soft" or _direction(s) is None:
            continue
        for j, h in enumerate(cons):
            if j in drop or h.strictness != "hard" or h.field != s.field:
                continue
            if _direction(h) == _direction(s) and _implies(h, s):
                drop.add(i)
                details.append(f"soft {format_constraint(s)} implied by hard "
                               f"{format_constraint(h)}")
                break
    kept = [c for i, c in enumerate(cons) if i not in drop]
    return ir.model_copy(update={"constraints": kept}), "; ".join(details)


O1 = Rule("O1", "ir", _o1_pre, _o1_apply)

ALL_IR_RULES = (O2, O1)  # spec order


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
