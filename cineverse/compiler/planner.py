"""Logical plan: one canonical template for every IR (the reference semantics), and validation.

`PlanNode`/`LogicalPlan` are the contract types; `build_plan` is a compiler function that reads the
candidate budget from RuntimeConfig (T01 review C4). The planner never prunes; O3/O4 do.
Spec: CineVerse_IR_and_Execution_Plan_Specification §4, §5.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from cineverse.compiler.ir import CompiledQuery, Constraint, format_constraint
from cineverse.config import RuntimeConfig

OutType = Literal["MovieSet", "RankedList", "Results"]
SOURCES = ("SemanticSearch", "MetadataSearch", "PopularityRank")
# operator -> (allowed input counts, input type, output type)
SIGNATURES: dict[str, tuple[tuple[int, ...], str | None, OutType]] = {
    "Scan": ((0,), None, "MovieSet"),
    "Mask": ((1,), "MovieSet", "MovieSet"),
    "SemanticSearch": ((1,), "MovieSet", "RankedList"),
    "MetadataSearch": ((1,), "MovieSet", "RankedList"),
    "PopularityRank": ((1,), "MovieSet", "RankedList"),
    "FilterList": ((1,), "RankedList", "RankedList"),
    "Fuse": ((1, 2, 3), "RankedList", "RankedList"),
    "SoftScore": ((1,), "RankedList", "RankedList"),
    "Diversify": ((1,), "RankedList", "RankedList"),
    "TopK": ((1,), "RankedList", "RankedList"),
    "Explain": ((1,), "RankedList", "Results"),
}


@dataclass
class PlanNode:
    id: str
    op: str
    args: dict[str, Any]
    inputs: list[str]
    out_type: OutType

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "op": self.op, "args": _plain(self.args), "inputs": self.inputs,
                "out_type": self.out_type}


@dataclass
class LogicalPlan:
    nodes: dict[str, PlanNode] = field(default_factory=dict)
    sink: str = ""

    def add(self, node_id: str, op: str, inputs: list[str], **args: Any) -> str:
        self.nodes[node_id] = PlanNode(node_id, op, args, inputs, SIGNATURES[op][2])
        return node_id

    def consumers(self, node_id: str) -> list[str]:
        return [n.id for n in self.nodes.values() if node_id in n.inputs]

    def to_dict(self) -> dict[str, Any]:
        return {"sink": self.sink, "nodes": [n.to_dict() for n in self.nodes.values()]}

    def validate(self) -> list[str]:
        """Rules 1–6 of IR Spec §5; empty list = valid."""
        errors: list[str] = []
        used = {i for n in self.nodes.values() for i in n.inputs}
        sinks = [n for n in self.nodes if n not in used]
        if len(sinks) != 1 or sinks[0] != self.sink:
            errors.append(f"1: expected one sink, found {sinks} (declared {self.sink!r})")
        elif self.nodes[self.sink].op not in ("Explain", "TopK"):
            errors.append(f"1: sink {self.sink} is {self.nodes[self.sink].op}")
        for n in self.nodes.values():
            missing = [i for i in n.inputs if i not in self.nodes]
            if missing:
                errors.append(f"2: {n.id} has missing inputs {missing}")
        if not errors and _has_cycle(self):
            errors.append("2: plan has a cycle")
        for n in self.nodes.values():
            counts, in_type, _ = SIGNATURES.get(n.op, ((), None, "Results"))
            if n.op not in SIGNATURES:
                errors.append(f"3: unknown operator {n.op}")
                continue
            if len(n.inputs) not in counts:
                errors.append(f"3: {n.id} ({n.op}) has {len(n.inputs)} inputs")
            for i in n.inputs:
                if i in self.nodes and self.nodes[i].out_type != in_type:
                    kind = "5" if n.op == "Fuse" else "3"
                    errors.append(f"{kind}: {n.id} expects {in_type} from {i}")
            preds = n.args.get("preds", []) if n.op in ("Mask", "FilterList") else []
            if any(c.strictness != "hard" for c in preds):
                errors.append(f"4: {n.id} has a soft predicate")
            soft = n.args.get("soft", []) if n.op == "SoftScore" else []
            if any(c.strictness != "soft" for c in soft):
                errors.append(f"4: {n.id} has a hard constraint in soft")
            followers = [self.nodes[c].op for c in self.consumers(n.id)]
            if n.op in SOURCES and n.args.get("c") == "N" and followers != ["FilterList"]:
                errors.append(f"6: {n.id} has c=N but is not followed by a FilterList")
        return errors


def _has_cycle(plan: LogicalPlan) -> bool:
    state: dict[str, int] = {}

    def visit(node_id: str) -> bool:
        if state.get(node_id) == 1:
            return True
        if state.get(node_id) == 2:
            return False
        state[node_id] = 1
        if any(visit(i) for i in plan.nodes[node_id].inputs):
            return True
        state[node_id] = 2
        return False

    return any(visit(n) for n in plan.nodes)


def _plain(value: Any) -> Any:
    if isinstance(value, Constraint):
        return format_constraint(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


def positives(ir: CompiledQuery) -> tuple[list[str], list[str]]:
    """pos_genres (positive genre preferences ∪ hard HAS) and pos_terms, both sorted."""
    genres = {p.value for p in ir.preferences if p.kind == "genre" and p.polarity == 1}
    genres |= {str(c.value) for c in ir.constraints
               if c.field == "genre" and c.op == "HAS" and c.strictness == "hard"}
    terms = sorted({p.value for p in ir.preferences if p.kind == "text" and p.polarity == 1})
    return sorted(genres), terms


def build_plan(ir: CompiledQuery, cfg: RuntimeConfig) -> LogicalPlan:
    """The canonical template (IR Spec §4): every source exhaustive, then FilterList."""
    hard = [c for c in ir.constraints if c.strictness == "hard"]
    soft = [c for c in ir.constraints if c.strictness == "soft"]
    pos_genres, pos_terms = positives(ir)
    c = cfg.candidate_budget

    plan = LogicalPlan()
    plan.add("s0", "Scan", [])
    fused: list[str] = []
    if ir.channels.semantic:
        plan.add("a1", "SemanticSearch", ["s0"], text=ir.semantic_text, c="N")
        fused.append(plan.add("a2", "FilterList", ["a1"], preds=hard, c=c))
    plan.add("b1", "MetadataSearch", ["s0"], genres=pos_genres, terms=pos_terms, c="N")
    fused.append(plan.add("b2", "FilterList", ["b1"], preds=hard, c=c))
    if not pos_genres and not pos_terms:
        plan.add("p1", "PopularityRank", ["s0"], c="N")
        fused.append(plan.add("p2", "FilterList", ["p1"], preds=hard, c=c))
    plan.add("f", "Fuse", fused, k=ir.ranking.rrf_k)
    plan.add("r", "SoftScore", ["f"], prefs=list(ir.preferences), soft=soft)
    last = "r"
    if ir.ranking.diversity == "mmr":
        last = plan.add("d", "Diversify", ["r"], **{"lambda": ir.ranking.mmr_lambda,
                                                    "n": ir.output.limit})
    plan.add("t", "TopK", [last], n=ir.output.limit)
    plan.sink = "t"
    if ir.output.explain:
        plan.sink = plan.add("x", "Explain", ["t"])
    return plan
