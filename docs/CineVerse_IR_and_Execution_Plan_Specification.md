# CineVerse — IR and Execution Plan Specification
**IR and Execution Plan Specification · v1.0**

Team 14 (Santhoshraja S, Siddharth P, Keshore G) · 2026-10-14 · Status: Draft for team review

---

> **Normative.** Defines the intermediate representation (`CompiledQuery`), its semantics, lowering, serialisation and versioning; the logical plan and its template; SSA instructions and their printed form; and the executor. Code in `compiler/ir.py`, `compiler/planner.py`, `compiler/codegen.py`, `compiler/driver.py` and `runtime/executor.py` must match it.

## Contents
1. Stage Interfaces · 2. The IR · 3. Lowering Examples · 4. Logical Plan · 5. Plan Validation · 6. Instructions and Printed Form · 7. Executor · 8. Test Obligations

## 1. Stage Interfaces
```
text ──lex──▶ list[Token] ──parse──▶ RequestNode ──analyse──▶ SemanticResult
     ──lower──▶ CompiledQuery ──run_ir_passes (O2, O1)──▶ CompiledQuery
     ──build_plan──▶ LogicalPlan ──optimize (O3, O4)──▶ LogicalPlan
     ──generate──▶ list[Instruction] ──execute──▶ ExecutionResult
```

| Function | Module | Signature |
|---|---|---|
| `lex` | `cineverse/compiler/lexer.py` | `lex(text: str, registry: DomainRegistry) -> tuple[list[Token], list[Diagnostic]]` |
| `parse` | `cineverse/compiler/parser.py` | `parse(tokens: list[Token], source: str) -> tuple[RequestNode, list[Diagnostic]]` |
| `analyse` | `cineverse/compiler/semantic.py` | `analyse(ast: RequestNode, registry: DomainRegistry) -> SemanticResult` |
| `lower` | `cineverse/compiler/ir.py` | `lower(sem: SemanticResult, registry: DomainRegistry) -> CompiledQuery` |
| `run_ir_passes` | `cineverse/compiler/passes.py` | `run_ir_passes(ir: CompiledQuery, enabled: set[str]) -> tuple[CompiledQuery, RuleLog]` |
| `build_plan` | `cineverse/compiler/planner.py` | `build_plan(ir: CompiledQuery, cfg: RuntimeConfig) -> LogicalPlan` |
| `optimize` | `cineverse/compiler/optimizer.py` | `optimize(plan: LogicalPlan, ir: CompiledQuery, caps: Capabilities, enabled: set[str]) -> tuple[LogicalPlan, RuleLog]` |
| `generate` | `cineverse/compiler/codegen.py` | `generate(plan: LogicalPlan) -> list[Instruction]` |
| `compile` | `cineverse/compiler/driver.py` | `compile(text: str, *, optimize: bool = True, rules: set[str] = ALL_RULES) -> CompilationResult` |
| `execute` | `cineverse/runtime/executor.py` | `execute(program: list[Instruction], ctx: RuntimeContext) -> ExecutionResult` |
| `recommend` | `cineverse/__init__.py` | `recommend(text: str, *, optimize: bool = True) -> tuple[CompilationResult, ExecutionResult \| None]` |

`CompilationResult` fields: `source, tokens, ast, semantic, ir_lowered, ir, plan_unoptimized, plan, rule_log, program, diagnostics, ok: bool, timings_ms: dict[str, float]`. `ok` is false if any diagnostic has severity ERROR; then `ir`, `plan` and `program` may be `None` and nothing is executed.

## 2. The IR
```python
class Preference(BaseModel):
    kind: Literal["genre", "text"]; value: str; polarity: Literal[1, -1]

class Constraint(BaseModel):
    field: Literal["genre", "year", "rating", "votes", "runtime", "language"]
    op: Literal["HAS", "NOT_HAS", "<=", ">=", "<", ">"]   # "<" ">" allowed only before O2, only on float fields after O2
    value: str | int | float
    strictness: Literal["hard", "soft"]
    span: tuple[int, int]

class Channels(BaseModel): semantic: bool; metadata: bool = True
class Ranking(BaseModel):
    fusion: Literal["rrf"] = "rrf"; rrf_k: int = 60
    diversity: Literal["none", "mmr"] = "none"; mmr_lambda: float = 0.7
class Output(BaseModel): limit: int = Field(10, ge=1, le=50); explain: bool = True

class CompiledQuery(BaseModel):
    ir_version: Literal["1.0"] = "1.0"
    source: str
    semantic_text: str
    preferences: list[Preference]
    constraints: list[Constraint]
    channels: Channels
    ranking: Ranking
    output: Output
    diagnostics: list[DiagnosticModel] = []
    def to_json(self) -> str            # sorted keys, no whitespace variance
    def hash(self) -> str               # sha256(to_json() without source, diagnostics, span fields)
    @classmethod
    def from_json(cls, s: str) -> "CompiledQuery"   # rejects other major versions
```

Lowering:
- soft annotations with field `genre`/`text` → `Preference`; soft numeric → `Constraint(strictness="soft")`.
- hard annotations → `Constraint(strictness="hard")`. `applied=False` annotations are not lowered.
- `semantic_text` = space-joined positive `text` preferences in source order, then display names of positive soft genres and hard-HAS genres, lower-case, de-duplicated. Never contains a polarity −1 term or a NOT_HAS genre.
- `channels.semantic` = registry capability; `ranking.diversity` = "mmr" iff a DiversityClause exists and mmr is available (else S105 WARNING with field "diversity": the request is served without diversification).

Validators (raise in tests, convert to S-diagnostics in the driver):
V1 field available; V2 op valid for field; V3 no genre both hard HAS and NOT_HAS; V4 `semantic_text` contains no negative term; V5 after passes, `preferences` and `constraints` sorted by `(field/kind, op, str(value))` and unique, and int fields use only `<=`/`>=`.

IR semantics (the reference meaning that all plans must implement):
eligible = {d ∈ catalogue : d satisfies every hard constraint; unknown value ⇒ not satisfied}; each eligible d gets `Score(d)` (Recommendation Engine Specification, soft scoring) computed from lists produced over the eligible set; result = first `limit` of eligible sorted by (−round(Score, 6), movie_id). Candidate truncation to C per channel is part of the semantics.

### 2.1 Serialisation and versioning rules
| Rule | Detail |
|---|---|
| Canonical JSON | `json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)` |
| Hash | SHA-256 hex of canonical JSON after removing `source`, `diagnostics` and every `span` field |
| Version | `ir_version` "MAJOR.MINOR". Same major: accept (missing optional fields take defaults). Different major: reject with `IRVersionError` |
| Round trip | `CompiledQuery.from_json(q.to_json()) == q` for every benchmark IR |
| Immutability | Models are frozen (`model_config = ConfigDict(frozen=True)`); passes return new objects |

## 3. Lowering Examples

| Request | IR highlights (after passes) |
|---|---|
| "no romance" | `constraints=[genre NOT_HAS Romance (hard)]`, `semantic_text=""`, no preferences |
| "little romance, comedy" | `preferences=[genre Comedy +1, genre Romance −1]`, `semantic_text="comedy"` |
| "between 2000 and 2010" | `year >= 2000`, `year <= 2010` (hard) |
| "90s" | `year >= 1990`, `year <= 1999` (hard) |
| "preferably after 2000" | `year >= 2001` (soft) |
| "rated above 4" | `rating > 4.0` (hard; float, not rewritten) |
| "top 100" | `output.limit = 50`, S109 |

See `CineVerse_Example_Requests_and_Expected_Outputs.json` for 25 complete IRs.

## 4. Logical Plan
```python
@dataclass
class PlanNode:
    id: str; op: str; args: dict; inputs: list[str]; out_type: Literal["MovieSet", "RankedList", "Results"]
@dataclass
class LogicalPlan:
    nodes: dict[str, PlanNode]; sink: str
    def validate(self) -> list[str]   # acyclic, inputs exist, types match op signature, single sink
```

Canonical (unoptimized) plan. The planner lowers **every** IR with the same template and leaves pruning to the optimizer.

Definitions: `pos_genres` = genres of positive genre preferences ∪ genres of hard `HAS` constraints (sorted); `pos_terms` = values of positive `text` preferences (sorted); `hard` = hard constraints; `soft` = soft constraints; *positives exist* ⇔ `pos_genres` or `pos_terms` is non-empty.

```
s0  = Scan()
a1  = SemanticSearch(text=ir.semantic_text, scope=s0, c=N)          # emitted iff channels.semantic
a2  = FilterList(a1, preds=hard, c=C)
b1  = MetadataSearch(genres=pos_genres, terms=pos_terms, scope=s0, c=N)
b2  = FilterList(b1, preds=hard, c=C)
p1  = PopularityRank(scope=s0, c=N)                                  # emitted iff NO positives exist
p2  = FilterList(p1, preds=hard, c=C)
f   = Fuse([a2, b2, p2], k=rrf_k)                                    # inputs that exist, in this order
r   = SoftScore(f, prefs=ir.preferences, soft=soft)
d   = Diversify(r, lambda=mmr_lambda, n=limit)                       # emitted iff ranking.diversity == "mmr"
t   = TopK(r or d, n=limit)
x   = Explain(t)                                                     # emitted iff output.explain
```

`SemanticSearch` with empty text and `MetadataSearch` with no genres and no terms are defined to return an empty list. `PopularityRank` ranks the scope by `bayes` (then `movie_id`); it is the only source when the request has no positive preference ("no romance", "after 2015, rated at least 4").

N = catalogue size; C = `runtime.yaml: candidate_budget` (default 200). FilterList with an empty predicate list only truncates to C.

### 4.1 Operator signatures
| Operator | Inputs | Output | Args |
|---|---|---|---|
| Scan | — | MovieSet | — |
| Mask | MovieSet | MovieSet | `preds: list[Constraint]` (hard) |
| SemanticSearch | MovieSet | RankedList | `text: str, c: int\|"N"` |
| MetadataSearch | MovieSet | RankedList | `genres: list[str], terms: list[str], c` |
| PopularityRank | MovieSet | RankedList | `c` |
| FilterList | RankedList | RankedList | `preds, c` |
| Fuse | RankedList × (1–3) | RankedList | `k` |
| SoftScore | RankedList | RankedList | `prefs, soft` |
| Diversify* | RankedList | RankedList | `lambda, n` |
| TopK | RankedList | RankedList | `n` |
| Explain | RankedList | Results | — |

## 5. Plan Validation
`LogicalPlan.validate()` returns a list of errors (empty = valid):
1. Exactly one sink; it is `Explain` or `TopK`.
2. Acyclic; every input id exists.
3. Input count and types match the signature table.
4. Every `Mask`/`FilterList` predicate is hard; every `SoftScore` soft constraint is soft.
5. Every source feeding `Fuse` is a RankedList.
6. `c` is `"N"` only in unoptimized sources followed by a FilterList.

## 6. Instructions and Printed Form
```python
@dataclass(frozen=True)
class Instruction:
    dest: str | None        # "%a1" (SSA: assigned once)
    opcode: str
    operands: tuple         # registers ("%s0") or literals
```

| Opcode | Operands | Result | Runtime function |
|---|---|---|---|
| SCAN | — | MovieSet | `catalog.all_ids()` |
| MASK | MovieSet, preds | MovieSet | `constraints.mask(catalog, scope, preds)` |
| SEM_SEARCH | text, scope, c | RankedList | `semantic_index.search(text, scope, c)` |
| META_SEARCH | genres, terms, scope, c | RankedList | `metadata_search.search(catalog, genres, terms, scope, c)` |
| POP_RANK | scope, c | RankedList | `metadata_search.popularity(catalog, scope, c)` |
| FILTER_LIST | RankedList, preds, c | RankedList | `constraints.filter_list(catalog, rl, preds, c)` |
| RRF | RankedList…, k | RankedList | `fusion.rrf(lists, k, z)` |
| SOFT | RankedList, prefs, soft | RankedList | `scoring.soft_score(catalog, rl, prefs, soft, cfg)` |
| MMR | RankedList, λ, n | RankedList | `diversity.mmr(...)` (optional) |
| TOPK | RankedList, n | RankedList | `rl.top(n)` |
| EXPLAIN | RankedList | Results | `explain.explain(catalog, rl, trace)` |
| RET | Results | — | — |

Generation = topological order of the plan DAG, ties broken by node id (lexicographic); registers are named after node ids (`s0, m1, a1, a2, b1, b2, p1, p2, f, r, d, t, x`).

Printed form (used in the UI, traces, golden files and `CineVerse_Example_Requests_and_Expected_Outputs.json`):

```
%s0 = SCAN
%m1 = MASK %s0, [genre NOT_HAS Musical, year >= 2011]
%a1 = SEM_SEARCH "comedy animation", %m1, c=200
%b1 = META_SEARCH genres=[Animation, Comedy], terms=[], %m1, c=200
%p1 = POP_RANK %m1, c=200
%a2 = FILTER_LIST %a1, [year >= 2011], c=200
%f = RRF %a1, %b1, k=60
%r = SOFT %f, prefs=[genre:Mystery+, genre:Romance-, text:thoughtful+], soft=[year >= 2001]
%d = MMR %r, lambda=0.7, n=10
%t = TOPK %r, n=10
%x = EXPLAIN %t
RET %x
```

Predicates print as `field OP value` in IR order; unoptimized searches print `c=N`.

## 7. Executor
1. Validate: opcode known; each register operand defined earlier and assigned once; operand types match the table.
2. Run sequentially; record `{index, opcode, dest, ms, out_size, sample(first 5 ids)}` in the trace.
3. Failure policy: SEM_SEARCH raising `IndexUnavailable` or `ModelUnavailable` → X201, result = empty RankedList. Empty eligible set → X202, empty results. Any other exception → ERROR diagnostic, stop, partial trace.

### 7.1 Execution record (per instruction)
```json
{"index": 3, "opcode": "SEM_SEARCH", "dest": "%a1", "ms": 18.4, "out_size": 200,
 "sample": [79132, 109487, 1196, 4370, 2571], "status": "ok"}
```
`status` ∈ `ok | fallback (X201) | empty (X202) | error`.

## 8. Test Obligations
| Area | Tests |
|---|---|
| IR | V1–V5; round trip; hash ignores source/spans/diagnostics; version accept/reject; frozen |
| Lowering | every annotation kind; BETWEEN, DECADE; `semantic_text` order and exclusion of negatives |
| Planner | template for: positives only; no positives (PopularityRank); semantic unavailable; mmr; explain false |
| Validation | each of the 6 rules has a failing fixture |
| Codegen | topological order with id ties; SSA; printed form matches the example JSON exactly |
| Executor | unknown opcode; use-before-def; double assignment; type mismatch; X201; X202; partial trace on exception |
