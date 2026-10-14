# T01 — Specification Review

Date: 2026-10-14 · Scope: the six normative specifications, the Example Requests JSON, and every
other document in `docs/` where it repeats a normative name.

## 1. Name consistency

| Name family | Documents compared | Result |
|---|---|---|
| Token types (22) | Frontend §3.1, Master §B.3, Deep Dive §3, Report §5.2 | Identical |
| AST node classes and fields | Frontend §5, Master §B.5, Deep Dive §4 | Identical. Report §5.4 uses `list[...]` and `LT/LE/GT/GE` (non-normative; spec wins) |
| Diagnostic codes and templates (19) | Frontend §7, Master §B.7, Deep Dive §6, Report §6.3 | Identical codes; Report paraphrases messages (non-normative) |
| IR models and fields | IR §2, Master §B.8, Deep Dive §7, Report §7.1 | Identical except Report: `Channels.metadata` has no default and `diagnostics: list[Diagnostic]` (spec: `DiagnosticModel`, default `[]`) |
| Opcodes (12) | IR §6, Master §B.9, Deep Dive §10, Report §8.2 | Identical |
| Plan operators and node ids | IR §4, Repository Standards §3 | Identical (`s0 m1 a1 a2 b1 b2 p1 p2 f r d t x`) |
| Rule ids O1–O4 | Optimizer §3–4, all others | Identical |
| Config keys | Configuration §2–3, DB Schemas §4, Engine §6, Master §B.11 | Identical |
| Stage function signatures | IR §1, Architecture §5.1, Master §B.2 | Identical |
| Catalogue columns | Dataset §2, DB Schemas §2 | Identical (DB Schemas adds Arrow types) |

## 2. Conflicts and missing definitions

Each item gives the proposed resolution used by the build. Items marked **(team)** fill a gap the
spec leaves open and need team confirmation; the others follow the normative spec.

| # | Where | Issue | Resolution |
|---|---|---|---|
| C1 | Engine §2.1 vs IR §6 opcode table | `explain(catalog, rl, ir)` vs `explain.explain(catalog, rl, trace)`; `execute(program, ctx)` gives EXPLAIN no access to the IR it needs (`semantic_text`, hard constraints) | Use the typed signature `explain(catalog, rl, ir)`. **(team)** `execute(program, ctx, *, ir=None)` gains an optional keyword so EXPLAIN can receive the IR; without it reasons that need the IR are omitted |
| C2 | Deep Dive §9 vs Architecture §5.3, LR-2 | `Capabilities` is described with the optimizer, but `RuntimeContext` (runtime) holds it and runtime may not import `compiler.optimizer` | **(team)** Define `Capabilities` in `compiler/ir.py` (contract layer, importable by both) |
| C3 | IR §2 V5 | Sort key `(field/kind, op, str(value))`: preferences have no `op`. Examples (EX01) sort preferences by kind then value, ignoring polarity | **(team)** Preferences sort by `(kind, value, polarity)`; constraints by `(field, op, str(value), strictness)` |
| C4 | Layer Req. LR-3 vs IR §1 | `planner.py` is listed as a contract module (stdlib + Pydantic only) but `build_plan(ir, cfg: RuntimeConfig)` needs `cineverse.config` | Treat `PlanNode`/`LogicalPlan` as the contract and `build_plan` as an L4 function; importing `cineverse.config` (L1) is allowed for L4 |
| C5 | Roadmap Step 1 vs Master T02 | "First 20 benchmark items (2 per category)" vs "convert the 25 Example JSON entries" | Follow Master T02 (25 items); the remaining items are human task H1 |
| C6 | Frontend §6 S1 | S101 "looks like a genre, edit distance ≤ 2" has no vocabulary; short names (`war`, `sf`, `imax`) would flag ordinary words | **(team)** Compare WORD tokens of length ≥ 4 against canonical genre names and aliases of length ≥ 5; distance ≤ 2. Checked against all 25 examples (only EX21 `thriler` fires) |
| C7 | Optimizer §8 vs Example JSON `rules_fired` | `RuleApplication.detail` format is not specified, but T27 asserts rules fired | `detail` reproduces the Example JSON strings exactly (e.g. `O2: year > 2010 -> year >= 2011`) |
| C8 | Dataset §3 P1 vs DB Schemas §3 | P1 says record file sizes; the manifest schema has no size field | Follow the schema (normative storage format); sizes not recorded |
| C9 | Example JSON | `expected.ir.diagnostics` and `expected.diagnostics` are code lists; `CompiledQuery.diagnostics` is `list[DiagnosticModel]` | Tests compare codes only |
| C10 | Engine §4 | "Released {year} ({human bound})" — human bound wording undefined | **(team)** `from Y` for `>=`, `until Y` for `<=`, `Y1–Y2` for both |
| C11 | IR §2 lowering vs Example JSON | Whether IR passes run when `optimize=False`. EX25 `program_unoptimized` already shows O1/O2 applied | O2/O1 always run (controlled by `rules`); `optimize` controls only the plan rules O3/O4 |
| C12 | Frontend §6 S2 | "integer value in year domain" — domain is the catalogue range | Year domain from the catalogue: currently 1902–2018 |
| C13 | Report §3.3 REMOVE | Lists "Separate popularity channel" as removed; Decision D-07 and IR §4 add `PopularityRank` | Spec and decision log win; Report to be updated in T30 |
| C14 | Report §7.3 | Hash excludes source and diagnostics; IR §2.1 also excludes spans | IR spec wins |
| C15 | Engine §2.1 vs Deep Dive §13 | `Recommendation.reasons: list[str]` vs `tuple[str, ...]` | Frozen dataclass with tuples (Repository Standards §4: frozen runtime records) |

## 3. Conflicts

15 items above; none blocks the build. Items C1, C2, C3, C6 and C10 change no normative name or
schema but add a definition the spec lacks; they are recorded for the decision log.
