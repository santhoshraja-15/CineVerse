# CineVerse — Optimizer and Equivalence Testing Specification
**Optimizer and Equivalence Testing Specification · v1.0**

Team 14 (Santhoshraja S, Siddharth P, Keshore G) · 2026-10-14 · Status: Draft for team review

---

> **Normative.** Defines the four optimization rules, their order, preconditions, transformations and correctness arguments, the rule log, and the equivalence and behaviour-preservation tests that gate them. **An optimization changes how a plan runs, never what it returns.** Soft scoring and MMR change what is returned; they are runtime operators, never rules.

## Contents
1. Principles · 2. Pass Pipeline · 3. IR Rules O2, O1 · 4. Plan Rules O3, O4 · 5. Behaviour Preservation · 6. Equivalence Testing · 7. Property Tests · 8. Rule Log · 9. Performance Measurement · 10. Adding a Rule

## 1. Principles
1. Every rule = `(id, precondition, apply)`; `apply` is called only if `precondition` is true.
2. Every rule has a written preservation argument, a positive test, a negative (must-not-fire) test, and is covered by the equivalence suite.
3. Rules run in a fixed order: **O2 → O1** on the IR, then **O3 → O4** on the plan. Each runs once (no fixpoint needed: none re-enables an earlier rule).
4. A rule may be disabled individually (`compile(text, rules={...})`) for localisation.
5. No rule depends on data values except through declared capabilities (`exact_search`, `semantic_available`).

## 2. Pass Pipeline
```
lower ─▶ O2 canonicalise ─▶ O1 redundancy ─▶ build_plan ─▶ O3 dead operators ─▶ O4 pushdown ─▶ codegen
```

## 3. IR Rules O2, O1
Run order: **O2 then O1**. Each appends `RuleApplication(rule, before, after, detail)` to the `RuleLog`.

**O2 Expression canonicalisation.** For int fields (`year`, `votes`, `runtime`): `x > a → x >= a+1`; `x < b → x <= b−1`; (`==` never produced by the parser in v1.0). Float field `rating` unchanged. Sort and de-duplicate lists. Negative test: rating `> 4` stays `> 4`.

**O1 Redundant-condition elimination.** (a) duplicates removed (set semantics); (b) two **hard** bounds on one field and direction → keep the tighter; (c) a **soft** bound implied by a **hard** bound on the same field and direction (e.g. soft `year >= 2000` with hard `year >= 2011`) → drop the soft one. Negative tests: two soft bounds are **not** merged (penalties add); hard and soft in opposite directions are kept.

### 3.1 Correctness arguments
| Rule | Argument |
|---|---|
| O2 | Over integers, `x > a ⇔ x ≥ a+1` and `x < b ⇔ x ≤ b−1`. Preferences and constraints have set semantics, so sorting and removing duplicates cannot change the eligible set or any score |
| O1 (a) | Set semantics |
| O1 (b) | Two hard lower bounds `x ≥ a`, `x ≥ b` with `a ≤ b`: `x ≥ b ⇒ x ≥ a`, so the conjunction equals `x ≥ b`; same for upper bounds. Eligible set unchanged |
| O1 (c) | Soft `x ≥ a` with hard `x ≥ b`, `b ≥ a`: every eligible movie satisfies the soft bound, so v(c,d) = 0 for all eligible d; dropping it changes no score |
| O1 negative | Two soft bounds are **not** merged: each contributes its own μ penalty when violated, so merging would change scores |

## 4. Plan Rules O3, O4
Run order: **O3 then O4**. Each rule = `(id, precondition(plan, ir, caps) -> bool, apply(plan) -> plan)`.

**O3 Dead-operator elimination.** Pre: `SemanticSearch.text == ""`, or `MetadataSearch` has no genres and no terms (both happen exactly when no positives exist), or a node whose output reaches no sink. Apply: delete the node and the FilterList that consumes it; Fuse keeps its remaining inputs (at least `p2` remains, by construction of the template). Correct because an empty list contributes 0 to RRF and RRF is normalised by the constant Z (Recommendation Engine Specification, fusion). Benefit: skips the encoder call / a full scan.

**O4 Filter pushdown.** Pre: every hard predicate depends only on movie attributes (vacuously true for an empty list); `caps.exact_search is True` (flat FAISS or NumPy backend); runtime breaks ties by movie_id with 1e-6 rounding. Apply: if `hard` is non-empty insert `m1 = Mask(s0, preds=hard)` and let scope = `m1`, else scope = `s0`; rewrite every `X(scope=s0, c=N) → FilterList(preds, C)` (X = SemanticSearch, MetadataSearch, PopularityRank) into `X(scope=scope, c=C)`; all rewritten sources share the one Mask. Correct because filtering a ranked list preserves relative order and an exact search over the eligible subset yields that same order; truncation to C commutes. Refuses to fire when `caps.exact_search` is False (HNSW). Benefit: searches score |eligible| instead of N, return C instead of N; mask computed once.

### 4.1 Correctness arguments
| Rule | Argument |
|---|---|
| O3 | An empty RankedList contributes 0 to every movie's RRF sum. Scores are divided by the constant Z = 2/(k+1), not by the number of executed lists, so removing an empty source leaves every score unchanged. Removing an unused node cannot affect the sink |
| O4 | Let L be the full exact ranking of the catalogue by a source, and E the eligible set. FilterList(L, E) keeps L's relative order on E. An exact search over E ranks E by the same scores; ties are broken by `movie_id` and scores are rounded to 1e-6 identically, so the order is identical. Truncation to C commutes with both. Predicates read only movie attributes, so the Mask is the same for every source and can be shared |
| O4 negative | On an approximate index (HNSW, IVF), a scoped search can return different neighbours from a full search, so the precondition `caps.exact_search` must be false and the rule must not fire |

## 5. Behaviour Preservation (gate before any rule is written)
- Each benchmark item has a hand-written `baseline_spec` (Database and Data Schemas §5).
- `tests/test_preservation.py`: for every item, `execute(compile(text, optimize=False)).results == recommend_baseline(spec).results` comparing ids, order and scores at 1e-6.
- Pass rate must be 100% before Roadmap step 10 starts. A failure means either the compiler mis-lowered the request (fix compiler) or the gold spec is wrong (fix spec with review).

## 6. Equivalence Testing
`compiler/equivalence.py`:
```python
@dataclass
class EquivalenceReport:
    request_id: str
    rules: frozenset[str]          # rules enabled in the optimized run
    same_ids: bool
    same_scores: bool              # after round(score, 6)
    same_hard_outcomes: bool       # set of eligible ids identical
    same_diagnostics: bool
    ms_unoptimized: float
    ms_optimized: float

def check(text: str, ctx: RuntimeContext, rules: frozenset[str]) -> EquivalenceReport
```
`tests/test_equivalence.py` runs `check` for every benchmark item with: each rule alone; all rules. Any `False` fails the test with the request id, the rule set and a diff of the first differing rank. Results are written to `results/equivalence.csv` by `run_all`.

## 7. Property Tests
| Property | Generator | Assertion |
|---|---|---|
| O4 pushdown | 200 random hard predicate sets over year/rating/votes/genre + random semantic text from the descriptor lexicon | optimized == unoptimized |
| O2 idempotence | random int bounds | `O2(O2(ir)) == O2(ir)` |
| O1 soundness | random hard/soft bounds | eligible set and scores unchanged on the catalogue |
| Determinism | any benchmark item twice | byte-identical IR JSON and results |

Generators use `random.Random(seed=42)`; no extra dependency is required (Hypothesis is OPTIONAL).

## 8. Rule Log
```python
@dataclass
class RuleApplication:
    rule: Literal["O1", "O2", "O3", "O4"]
    level: Literal["ir", "plan"]
    detail: str
    before: dict
    after: dict
```
The UI lists applications in order; the trace stores them; golden programs in the example JSON list `rules_fired`.

## 9. Performance Measurement
For each benchmark item: median of 20 warm runs of execution with optimizer off and on, per instruction. Report median speed-up overall and split by hard-filter selectivity (eligible / N < 0.1, 0.1–0.5, > 0.5). No speed-up is claimed for a category until measured.

## 10. Adding a Rule (process)
1. Write the precondition, transformation and preservation argument in this document.
2. Add positive, negative and equivalence coverage.
3. Implement behind a flag; run equivalence with the rule alone, then all rules.
4. Record in CHANGELOG and Project Control decision log.
Candidate (OPTIONAL): **O5 common-subexpression reuse** of the query embedding by MMR.
