"""Plan rules, run in order O3 then O4; each application is logged. Never changes results.

O3 removes sources that are provably empty (SemanticSearch with empty text, MetadataSearch with no
genres and no terms) together with their FilterList, and nodes that reach no sink. O4 pushes the
hard filter and the truncation into the sources through one shared Mask; it refuses unless search
is exact.
Spec: CineVerse_Optimizer_and_Equivalence_Testing_Specification §4, §4.1, §8.
"""

from __future__ import annotations

import copy

from cineverse.compiler.ir import Capabilities, CompiledQuery, format_constraint
from cineverse.compiler.passes import Rule, RuleApplication, RuleLog
from cineverse.compiler.planner import SOURCES, LogicalPlan, PlanNode


def _empty_sources(plan: LogicalPlan) -> list[str]:
    def empty(n: PlanNode) -> bool:
        if n.op == "SemanticSearch":
            return n.args.get("text") == ""
        return n.op == "MetadataSearch" and not n.args.get("genres") and not n.args.get("terms")

    return sorted(n.id for n in plan.nodes.values() if empty(n))


def _unreachable(plan: LogicalPlan) -> list[str]:
    live, stack = set(), [plan.sink]
    while stack:
        node_id = stack.pop()
        if node_id in live:
            continue
        live.add(node_id)
        stack += plan.nodes[node_id].inputs
    return sorted(set(plan.nodes) - live)


# --------------------------------------------------------------------------- O3


def _o3_pre(plan: LogicalPlan, ir: CompiledQuery, caps: Capabilities) -> bool:
    return bool(_empty_sources(plan) or _unreachable(plan))


def _o3_apply(plan: LogicalPlan) -> tuple[LogicalPlan, list[str]]:
    details = []
    for src in _empty_sources(plan):
        op = plan.nodes[src].op
        consumers = plan.consumers(src)
        removed = [src] + [c for c in consumers if plan.nodes[c].op == "FilterList"]
        for node_id in removed:
            for other in plan.nodes.values():
                if node_id in other.inputs:
                    other.inputs = [i for i in other.inputs if i != node_id]
        for node_id in removed:
            del plan.nodes[node_id]
        tail = f" and {removed[1]}" if len(removed) > 1 else ""
        details.append(f"removed {src} ({op}){tail}")
    for node_id in _unreachable(plan):
        del plan.nodes[node_id]
        details.append(f"removed unused {node_id}")
    return plan, details


O3 = Rule("O3", "plan", _o3_pre, _o3_apply)


# --------------------------------------------------------------------------- O4


def _pushable(plan: LogicalPlan) -> list[tuple[str, str]]:
    """(source, its FilterList) pairs of the canonical form X(scope=s0, c=N) -> FilterList."""
    pairs = []
    for n in sorted(plan.nodes.values(), key=lambda n: n.id):
        if n.op in SOURCES and n.args.get("c") == "N":
            consumers = plan.consumers(n.id)
            if len(consumers) == 1 and plan.nodes[consumers[0]].op == "FilterList":
                pairs.append((n.id, consumers[0]))
    return pairs


def _o4_pre(plan: LogicalPlan, ir: CompiledQuery, caps: Capabilities) -> bool:
    """Exact search only (flat FAISS or NumPy); predicates read movie attributes only."""
    return caps.exact_search and bool(_pushable(plan))


def _o4_apply(plan: LogicalPlan) -> tuple[LogicalPlan, list[str]]:
    pairs = _pushable(plan)
    preds = list(plan.nodes[pairs[0][1]].args["preds"])
    scan = plan.nodes[pairs[0][0]].inputs[0]
    scope = scan
    if preds:
        scope = plan.add("m1", "Mask", [scan], preds=preds)
    for src, flt in pairs:
        source = plan.nodes[src]
        source.inputs = [scope]
        source.args["c"] = plan.nodes[flt].args["c"]
        for other in plan.nodes.values():
            other.inputs = [src if i == flt else i for i in other.inputs]
        del plan.nodes[flt]
    targets = ", ".join(src for src, _ in pairs)
    if preds:
        shown = ", ".join(format_constraint(c) for c in preds)
        return plan, [f"pushed MASK [{shown}] into {targets}"]
    return plan, [f"pushed truncation into {targets}"]


O4 = Rule("O4", "plan", _o4_pre, _o4_apply)

ALL_PLAN_RULES = (O3, O4)  # spec order


def optimize(
    plan: LogicalPlan, ir: CompiledQuery, caps: Capabilities, enabled: set[str]
) -> tuple[LogicalPlan, RuleLog]:
    """Apply O3 then O4 to a copy of the plan (the canonical plan is kept for the trace)."""
    plan = copy.deepcopy(plan)
    log: RuleLog = []
    for rule in ALL_PLAN_RULES:
        if rule.id not in enabled or not rule.precondition(plan, ir, caps):
            continue
        before = plan.to_dict()
        plan, details = rule.apply(plan)
        for detail in details:
            log.append(RuleApplication(rule.id, "plan", detail, before, plan.to_dict()))
    return plan, log
