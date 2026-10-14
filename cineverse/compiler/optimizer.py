"""Plan rules, run in order O3 then O4; each application is logged. Never changes results.

O3 removes sources that are provably empty (SemanticSearch with empty text, MetadataSearch with no
genres and no terms) together with their FilterList, and nodes that reach no sink. O4 pushes the
hard filter and the truncation into the sources through one shared Mask; it refuses unless search
is exact.
Spec: CineVerse_Optimizer_and_Equivalence_Testing_Specification §4, §4.1, §8.
"""

from __future__ import annotations

import copy

from cineverse.compiler.ir import Capabilities, CompiledQuery
from cineverse.compiler.passes import Rule, RuleApplication, RuleLog
from cineverse.compiler.planner import LogicalPlan, PlanNode


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


ALL_PLAN_RULES = (O3,)  # O4 is added in T25


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
