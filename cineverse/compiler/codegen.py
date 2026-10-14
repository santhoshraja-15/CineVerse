"""Code generation: plan DAG to SSA three-address instructions, and their printed form.

Topological order with ties broken by node id (lexicographic); one register per node.
Spec: CineVerse_IR_and_Execution_Plan_Specification §6.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Any

from cineverse.compiler.ir import Constraint, Preference, format_constraint
from cineverse.compiler.planner import LogicalPlan

OPCODES = {
    "Scan": "SCAN", "Mask": "MASK", "SemanticSearch": "SEM_SEARCH",
    "MetadataSearch": "META_SEARCH", "PopularityRank": "POP_RANK", "FilterList": "FILTER_LIST",
    "Fuse": "RRF", "SoftScore": "SOFT", "Diversify": "MMR", "TopK": "TOPK", "Explain": "EXPLAIN",
}


@dataclass(frozen=True)
class Instruction:
    dest: str | None  # "%a1" (SSA: assigned once)
    opcode: str
    operands: tuple[Any, ...]  # registers ("%s0") or literals

    def __str__(self) -> str:
        return format_instruction(self)


def reg(node_id: str) -> str:
    return f"%{node_id}"


def topological(plan: LogicalPlan) -> list[str]:
    """Kahn's algorithm, always taking the smallest ready node id."""
    pending = {n: len(node.inputs) for n, node in plan.nodes.items()}
    ready = [n for n, count in pending.items() if count == 0]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        n = heapq.heappop(ready)
        order.append(n)
        for consumer in sorted(plan.consumers(n)):
            pending[consumer] -= plan.nodes[consumer].inputs.count(n)
            if pending[consumer] == 0:
                heapq.heappush(ready, consumer)
    if len(order) != len(plan.nodes):
        raise ValueError("plan has a cycle")
    return order


def generate(plan: LogicalPlan) -> list[Instruction]:
    out: list[Instruction] = []
    for node_id in topological(plan):
        n = plan.nodes[node_id]
        ins = [reg(i) for i in n.inputs]
        a = n.args
        operands: tuple[Any, ...]
        if n.op == "Scan":
            operands = ()
        elif n.op == "Mask":
            operands = (ins[0], tuple(a["preds"]))
        elif n.op == "SemanticSearch":
            operands = (a["text"], ins[0], a["c"])
        elif n.op == "MetadataSearch":
            operands = (tuple(a["genres"]), tuple(a["terms"]), ins[0], a["c"])
        elif n.op == "PopularityRank":
            operands = (ins[0], a["c"])
        elif n.op == "FilterList":
            operands = (ins[0], tuple(a["preds"]), a["c"])
        elif n.op == "Fuse":
            operands = (*ins, a["k"])
        elif n.op == "SoftScore":
            operands = (ins[0], tuple(a["prefs"]), tuple(a["soft"]))
        elif n.op == "Diversify":
            operands = (ins[0], a["lambda"], a["n"])
        elif n.op == "TopK":
            operands = (ins[0], a["n"])
        else:  # Explain
            operands = (ins[0],)
        out.append(Instruction(reg(node_id), OPCODES[n.op], operands))
    out.append(Instruction(None, "RET", (reg(plan.sink),)))
    return out


# --------------------------------------------------------------------------- printed form


def _preds(preds: tuple[Constraint, ...]) -> str:
    return "[" + ", ".join(format_constraint(c) for c in preds) + "]"


def _prefs(prefs: tuple[Preference, ...]) -> str:
    items = (f"{p.kind}:{p.value}{'+' if p.polarity == 1 else '-'}" for p in prefs)
    return "[" + ", ".join(items) + "]"


def format_instruction(ins: Instruction) -> str:
    o = ins.operands
    op = ins.opcode
    if op == "SCAN":
        body = ""
    elif op == "MASK":
        body = f"{o[0]}, {_preds(o[1])}"
    elif op == "SEM_SEARCH":
        body = f'"{o[0]}", {o[1]}, c={o[2]}'
    elif op == "META_SEARCH":
        body = f"genres=[{', '.join(o[0])}], terms=[{', '.join(o[1])}], {o[2]}, c={o[3]}"
    elif op == "POP_RANK":
        body = f"{o[0]}, c={o[1]}"
    elif op == "FILTER_LIST":
        body = f"{o[0]}, {_preds(o[1])}, c={o[2]}"
    elif op == "RRF":
        body = ", ".join(o[:-1]) + f", k={o[-1]}"
    elif op == "SOFT":
        body = f"{o[0]}, prefs={_prefs(o[1])}, soft={_preds(o[2])}"
    elif op == "MMR":
        body = f"{o[0]}, lambda={o[1]}, n={o[2]}"
    elif op == "TOPK":
        body = f"{o[0]}, n={o[1]}"
    else:  # EXPLAIN, RET
        body = str(o[0])
    head = op if ins.dest is None else f"{ins.dest} = {op}"
    return f"{head} {body}".rstrip()


def print_program(program: list[Instruction]) -> list[str]:
    return [format_instruction(i) for i in program]
