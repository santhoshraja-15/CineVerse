# CineVerse — Complete Build Instructions for Claude Code
### Drift-proof, task-by-task build prompts aligned to the CineVerse specification set v1.0

Team 14 (Santhoshraja S, Siddharth P, Keshore G) · 2026-10-14 · v1.0

---

> **Purpose.** This playbook builds CineVerse from an empty repository to a tested, demo-ready system using Claude Code, one self-contained task at a time (T01–T30 CORE, T31–T34 OPTIONAL). It is both the **build instructions** and the **build prompt**: §A is the standing contract, §D holds the prompt for every task.

> **Alignment guarantee.** The normative sources are: Compiler Front-End Specification, IR and Execution Plan Specification, Optimizer and Equivalence Testing Specification, Recommendation Engine Specification, Dataset and Data Pipeline Specification, and Database and Data Schemas. §B copies their contracts verbatim. **If any prompt disagrees with a normative specification, the specification wins** — stop and report the conflict instead of choosing.

## Contents
§A Operating Contract · §B Canonical Specifications · §C Failure Modes and Their Guards · §D The Build (T01–T34) · §E Build Order · §F Final Acceptance

---

## §A. Operating Contract — save as `CLAUDE.md` at the repository root

```markdown
# CLAUDE.md — CineVerse operating contract

## What CineVerse is
A Compiler Design course project. It compiles a natural-language movie request
(lexer → parser → AST → semantic analysis → typed IR → IR passes → logical plan →
optimizer → SSA instructions) and executes the program on a hybrid recommendation
runtime (Sentence Transformers + FAISS, metadata and popularity ranking, RRF, hard and
soft constraints, evidence-based explanations). The compiler is the main deliverable.

## GROUND TRUTH (never change without an explicit instruction)
- Normative specs in docs/: Compiler_Frontend, IR_and_Execution_Plan, Optimizer_and_
  Equivalence_Testing, Recommendation_Engine, Dataset_and_Data_Pipeline,
  Database_and_Data_Schemas. Names, codes, opcodes, schemas and formulas come from them.
- Package layout and layer rules: docs/CineVerse_Repository_Structure_and_Coding_Standards.md
  and docs/CineVerse_Layer_Architecture_Requirements.md.
- cineverse.compiler never imports cineverse.runtime; cineverse.runtime never imports the
  lexer, parser, ast, semantic, passes or optimizer. They meet only at CompiledQuery,
  LogicalPlan and list[Instruction].
- Task order: docs/CineVerse_Implementation_Roadmap_and_Task_Checklist.md.

## ANTI-HALLUCINATION RULES (hard)
1. Never invent a module, class, function, field, token type, diagnostic code, opcode or
   rule id. If the spec does not define it, stop and ask one question.
2. Before using any third-party API (sentence-transformers, faiss, pydantic, pandas,
   pyarrow, streamlit), read the installed package's docs or source in this session and
   use only signatures you have confirmed. Never guess call shapes from memory.
3. Never add a dependency that is not in requirements.txt / requirements-dev.txt.
4. Import existing types; never redefine a type that already exists in the codebase.
5. Never fabricate output: no hand-typed metrics, no invented movie titles in fixtures
   except the documented toy catalogue, no claimed results without a run.

## ANTI-DRIFT RULES (hard)
1. Touch only the files the current task lists.
2. No refactors, renames or "improvements" outside the task.
3. Keep data models byte-aligned with the normative specs (field names, enums, order).
4. Do not implement OPTIONAL features (MMR, TMDB, FastAPI, SQLite feedback, HNSW)
   unless the task says so.
5. Do not write optimizer code (O1–O4) before T21 (behaviour preservation) passes.
6. Golden files are regenerated only by tests/golden/regenerate.py and every diff is
   reported.

## QUALITY GATES
- Python 3.11, type hints everywhere, `from __future__ import annotations`.
- ruff clean; mypy clean for cineverse/compiler.
- Compiler stages are pure functions; user problems are Diagnostic values, not exceptions.
- Every ranking sorts by (-round(score, 6), movie_id).
- INVIOLABLE INVARIANT: an optimization never changes results; hard constraints act
  only in MASK/FILTER_LIST and an unknown value never satisfies a hard constraint.

## WORKING METHOD
1. Read the task, then the spec sections it cites.
2. State a short plan (files, functions, tests).
3. Write the tests first, then the code.
4. Run the task's VERIFY commands; paste the output.
5. Update docs/CHANGELOG.md if an interface changed (only when the task allows it).
6. One commit per task: "Txx: <summary>".

## DEFINITION OF DONE (per task)
VERIFY passes; `pytest -q -m "not full"` green; ruff clean; only allowed files changed;
the task's checkbox ticked in the Roadmap.
```

---

## §B. Canonical Specifications (single source of truth)

### B.1 Environment variables (`.env.example`)
```
CINEVERSE_LOG_LEVEL=INFO
CINEVERSE_PERSIST_TRACES=0
# CINEVERSE_INDEX_BACKEND=numpy
# HF_HUB_OFFLINE=1
# TMDB_API_KEY=            # OPTIONAL, task T32 only
```

### B.2 Stage interfaces
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

### B.3 Token
```python
class TokenType(Enum):
    GENRE DESCRIPTOR NEG_HARD NEG_SOFT HEDGE STRICT CMP BETWEEN TO NUMBER DECADE UNIT FIELD
    LIMIT ITEM DIVERSE SEP OR FILLER WORD EOF

@dataclass(frozen=True, slots=True)
class Token:
    type: TokenType
    lexeme: str            # as in source (lower-cased)
    value: object          # normalised value (see table)
    span: tuple[int, int]  # [start, end) in the ORIGINAL text
```

### B.4 Grammar
```
request     ::= [ clause { [ SEP ] clause } ] EOF
clause      ::= limit | diversity | constraint | exclusion | preference
limit       ::= LIMIT [ NUMBER ] [ ITEM ]  |  NUMBER ITEM
diversity   ::= DIVERSE [ ITEM ]
constraint  ::= [ HEDGE ] [ FIELD ] comparison [ UNIT ]
comparison  ::= CMP quantity
              | BETWEEN quantity ( SEP("and") | TO ) quantity
              | DECADE
quantity    ::= NUMBER [ UNIT ]
exclusion   ::= [ HEDGE ] ( NEG_HARD | NEG_SOFT ) target { OR target }
preference  ::= [ HEDGE | STRICT ] term { [ OR ] term } [ ITEM ]
term        ::= GENRE | DESCRIPTOR | WORD
target      ::= GENRE | DESCRIPTOR | WORD
```

### B.5 AST
```python
Span = tuple[int, int]

@dataclass(frozen=True, slots=True)
class GenreTerm:       raw: str; genres: tuple[str, ...]; span: Span; node_id: int
class DescriptorTerm:  text: str; span: Span; node_id: int
Term = GenreTerm | DescriptorTerm

class NumberNode:      value: int | float; unit_raw: str | None; span: Span; node_id: int
class PreferenceClause: terms: tuple[Term, ...]; modifier: Literal["NONE","HEDGE","STRICT"]; has_or: bool; span; node_id
class ExclusionClause:  targets: tuple[Term, ...]; strength: Literal["HARD","SOFT"]; hedged: bool; span; node_id
class ConstraintClause: field_raw: str | None; op: Literal["<","<=",">",">=","BETWEEN","DECADE"];
                        values: tuple[NumberNode, ...]; unit_raw: str | None; hedged: bool; span; node_id
class LimitClause:      n: int | None; span; node_id
class DiversityClause:  span; node_id
class ErrorNode:        text: str; span; node_id
Clause = PreferenceClause | ExclusionClause | ConstraintClause | LimitClause | DiversityClause | ErrorNode

class RequestNode:      clauses: tuple[Clause, ...]; source: str; span; node_id
```
`PreferenceClause.has_or: bool` records whether OR joined its terms (rule S13).

### B.6 Semantic annotations
```python
@dataclass
class Annotation:
    kind: Literal["pref", "constraint", "limit", "diversity", "ignored"]
    field: str | None          # genre/year/rating/votes/runtime/language/text
    op: str | None             # HAS, NOT_HAS, <, <=, >, >=
    value: object              # canonical value(s) after conversion
    polarity: Literal[1, -1] | None
    strictness: Literal["hard", "soft"] | None
    applied: bool              # False when S105 drops it

@dataclass
class SemanticResult:
    ast: RequestNode
    annotations: dict[int, list[Annotation]]   # node_id -> annotations
    diagnostics: list[Diagnostic]
```

### B.7 Diagnostics
```python
class Severity(Enum): ERROR, WARNING, INFO
@dataclass(frozen=True)
class Diagnostic:
    code: str; severity: Severity; message: str; span: tuple[int, int] | None; hint: str | None
```
| Code | Sev | Message template |
|---|---|---|
| L001 | INFO | Ignored character '{ch}' |
| P001 | WARNING | Could not understand '{text}'; skipped |
| P002 | WARNING | Number {n} has no meaning here |
| S101 | INFO | '{word}' is not a known genre; used as a description |
| S102 | ERROR | Cannot tell what '{text}' refers to (year, rating, votes or runtime?) |
| S103 | ERROR | '{op}' cannot be used with {field} |
| S104 | ERROR | {value} is outside the range of {field} ({lo}–{hi}) |
| S105 | WARNING | {field} is not available in this catalogue; '{text}' was not applied |
| S106 | WARNING | '{text}' cannot be checked exactly; applied as a preference |
| S107 | ERROR | {genre} is both required and excluded |
| S108 | ERROR | No {field} satisfies all conditions |
| S109 | WARNING | Number of results limited to {n} |
| S110 | WARNING | Preference for {genre} overridden by a strict condition |
| S111 | ERROR | Nothing to recommend from; add a genre, mood or condition |
| S112 | INFO | Converted {from} to {to} |
| S113 | ERROR | Request is empty or longer than {max} characters |
| S114 | WARNING | 'only … or …' cannot be applied strictly; used as preferences |
| X201 | WARNING | Semantic search unavailable; results use metadata only |
| X202 | INFO | No movie satisfies all strict conditions |

### B.8 IR
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

### B.9 Plan and instructions
```python
@dataclass
class PlanNode:
    id: str; op: str; args: dict; inputs: list[str]; out_type: Literal["MovieSet", "RankedList", "Results"]
@dataclass
class LogicalPlan:
    nodes: dict[str, PlanNode]; sink: str
    def validate(self) -> list[str]   # acyclic, inputs exist, types match op signature, single sink
```
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

### B.10 Runtime types
```python
@dataclass(frozen=True)
class RankedList:
    ids: tuple[int, ...]            # rank = index + 1
    scores: tuple[float, ...]
    source: str                     # "semantic" | "metadata" | "rrf" | "soft" | "mmr" | "topk"
    evidence: dict[int, dict]       # per-movie evidence accumulated for explanations
```

### B.11 Configuration
```yaml
# config/registry.yaml
registry_version: "1.0"
genres:                       # canonical -> display name used in embed/semantic text
  Action: action
  Adventure: adventure
  Animation: animation
  Children: children's
  Comedy: comedy
  Crime: crime
  Documentary: documentary
  Drama: drama
  Fantasy: fantasy
  Film-Noir: film noir
  Horror: horror
  IMAX: imax
  Musical: musical
  Mystery: mystery
  Romance: romance
  Sci-Fi: science fiction
  Thriller: thriller
  War: war
  Western: western
genre_aliases:                # lexeme -> list of canonical genres
  sci-fi: [Sci-Fi]
  scifi: [Sci-Fi]
  science fiction: [Sci-Fi]
  sf: [Sci-Fi]
  rom-com: [Romance, Comedy]
  romcom: [Romance, Comedy]
  romantic comedy: [Romance, Comedy]
  animated: [Animation]
  cartoon: [Animation]
  kids: [Children]
  family: [Children]
  noir: [Film-Noir]
  scary: [Horror]
  funny: [Comedy]
  documentaries: [Documentary]
  musicals: [Musical]
  # plurals (comedies, thrillers, mysteries, ...) generated automatically
fields:
  genre:    {type: genre_set, ops: [HAS, NOT_HAS], available: true}
  year:     {type: int,   unit: year,    ops: ["<=", ">="], domain: from_catalog, available: true}
  rating:   {type: float, unit: stars,   ops: ["<=", ">="], domain: [0.5, 5.0],  available: true}
  votes:    {type: int,   unit: ratings, ops: ["<=", ">="], domain: [0, null],   available: true}
  runtime:  {type: int,   unit: minutes, ops: ["<=", ">="], domain: [1, 600],    available: false}
  language: {type: code,  ops: [HAS],    available: false}
units:
  stars: {field: rating, factor: 1}
  ratings: {field: votes, factor: 1}
  votes: {field: votes, factor: 1}
  minutes: {field: runtime, factor: 1}
  mins: {field: runtime, factor: 1}
  hours: {field: runtime, factor: 60}
  hrs: {field: runtime, factor: 60}
limit: {min: 1, max: 50, default: 10}
max_input_chars: 300
```
```yaml
# config/runtime.yaml
runtime_version: "1.0"
model_name: sentence-transformers/all-MiniLM-L6-v2
index_backend: faiss_flat        # faiss_flat | numpy  (both exact; hnsw only for the optional scale experiment)
candidate_budget: 200            # C
rrf_k: 60
score_round_decimals: 6
soft:
  beta: 0.10                     # bonus per matched positive soft preference
  lambda: 0.30                   # penalty per matched negative soft preference
  mu: 0.20                       # penalty per violated (or unknown) soft constraint
metadata:
  tag_match_weight: 0.5
  bayes_m: 10
mmr:                             # optional
  lambda: 0.7
seed: 42
```

### B.12 Repository structure
Fixed as in `docs/CineVerse_Repository_Structure_and_Coding_Standards.md` §1.

### B.13 Pinned stack
Python 3.11; pandas>=2.2,<3; numpy>=1.26,<3; pyarrow>=15; sentence-transformers>=3.0; faiss-cpu>=1.8; pydantic>=2.7,<3; pyyaml>=6; streamlit>=1.36; dev: pytest>=8, pytest-cov>=5, ruff>=0.6, mypy>=1.10, jsonschema>=4.22. Confirm the installed versions in T03 and lock them in `requirements.lock`.

---

## §C. How These Prompts Prevent the Three Failure Modes

| Failure mode | Guard in this document |
|---|---|
| Hallucinated APIs or shapes | §A rule "read installed docs first"; §B copied verbatim; every task names the exact spec section |
| Errors | Tests first in every task; VERIFY with exact commands; golden files; gates T21 and T25 |
| Drift | "Files you may touch" per task; explicit "Do NOT"; layer test; optimizer forbidden before T21 |

---

## §D. The Build — Task-by-Task Prompts

### PHASE 0 — Foundation

### T01 · Spec sign-off — `docs/` · [P0] · depends: —
> **PROMPT**
> Goal: confirm the specification set is internally consistent before coding.
> Files you may touch: `docs/status/T01_review.md` only.
> Requirements:
> 1. Read every normative spec and the Example Requests JSON.
> 2. List every name (module, class, field, code, opcode, rule) that appears in more than one document and check it is spelled identically.
> 3. List any contradiction or missing definition with document and section.
> Do NOT edit any spec; report only.
> **VERIFY:** `docs/status/T01_review.md` exists with a "Conflicts" section (empty or listed).

---

### T02 · Benchmark seed — `benchmark/requests.jsonl` · [P0] · depends: T01
> **PROMPT**
> Goal: create the benchmark file with the 25 entries of `docs/CineVerse_Example_Requests_and_Expected_Outputs.json` converted to the benchmark format (Database and Data Schemas §5).
> Files you may touch: `benchmark/requests.jsonl`, `scripts/examples_to_benchmark.py`.
> Requirements:
> 1. Map `expected.ir` → `gold_ir` (drop `source`, `diagnostics`), `expected.diagnostics` → `gold_diagnostics`.
> 2. Generate `baseline_spec` from `gold_ir` exactly as defined in Database and Data Schemas §5; `null` for invalid items.
> 3. Assign `split` = "dev" for EX01–EX10, "test" for the rest (the team replaces this split when the full benchmark is written).
> Do NOT invent new requests; the remaining 95 are written by the team (H1).
> **VERIFY:** `python scripts/examples_to_benchmark.py && python -c "import json;[json.loads(l) for l in open('benchmark/requests.jsonl')];print('ok')"`.

---

### T03 · Repository and environment — repo root · [P0] · depends: T01
> **PROMPT**
> Goal: execute `docs/CineVerse_Tech_Stack_Master_Prompt.md` §2 exactly.
> Files you may touch: everything listed in that prompt.
> Requirements: as in that prompt; also create `CLAUDE.md` from §A of this document, `.gitignore` (data/, artifacts/, traces/, logs/, .env, .venv/), `scripts/check.sh` and `scripts/check.ps1` running ruff and the fast test suite.
> Do NOT implement any stage.
> **VERIFY:** `ruff check . && pytest -q` → smoke and layer tests pass; `requirements.lock` exists.

---

### T04 · Dataset preparation — `cineverse/data/prepare.py`, `cineverse/runtime/catalog.py` · [P0] · depends: T03
> **PROMPT**
> Goal: implement Dataset and Data Pipeline Specification §2–§4 and §6.
> Files you may touch: `cineverse/data/prepare.py`, `cineverse/runtime/catalog.py`, `cineverse/config.py`, `tests/test_prepare.py`, `tests/test_catalog.py`, `tests/fixtures/toy_movielens/*`.
> Requirements:
> 1. Steps P1–P9 exactly; checks D1–D7 with the specified failure behaviour.
> 2. Catalogue columns and types exactly as Database and Data Schemas §2.
> 3. Manifest keys exactly as Database and Data Schemas §3.
> 4. `Catalog.load`, `all_ids`, `get`, `column` as in Recommendation Engine Spec §2.1.
> Do NOT read CSVs anywhere else; do NOT add enrichment.
> **VERIFY:** `pytest -q tests/test_prepare.py tests/test_catalog.py`; with real data: `python -m cineverse.data.prepare` prints row counts and coverage and writes `data/processed/catalog.parquet`.

---

### PHASE 1 — Runtime and baseline (the target machine)

### T05 · Embeddings and index build — `cineverse/runtime/embeddings.py`, `cineverse/data/build_index.py` · [P0] · depends: T04
> **PROMPT**
> Goal: implement Dataset Spec §5 (I1–I6).
> Files you may touch: those two files, `tests/test_build_index.py`.
> Requirements:
> 1. Read the installed sentence-transformers docs for `SentenceTransformer` and `encode` before coding.
> 2. Encode `embed_text` with `normalize_embeddings=True`, batch 64, float32; save `embeddings.npy`, `ids.npy`.
> 3. If backend is faiss_flat, build `IndexIDMap(IndexFlatIP(384))` with `add_with_ids`; write `faiss.index`.
> 4. Self-retrieval check I5; manifest update I6.
> 5. Tests use a 20-movie toy catalogue and a stub encoder (deterministic vectors), not the real model.
> Do NOT use any other model or index type.
> **VERIFY:** `pytest -q tests/test_build_index.py`; with real data `python -m cineverse.data.build_index` prints "self-check 50/50".

---

### T06 · Semantic index — `cineverse/runtime/semantic_index.py` · [P0] · depends: T05
> **PROMPT**
> Goal: implement Recommendation Engine Spec §2 (11.2) with two exact backends.
> Files you may touch: `cineverse/runtime/semantic_index.py`, `cineverse/runtime/context.py`, `tests/test_semantic_index.py`.
> Requirements:
> 1. `FaissFlatIndex` and `NumpyIndex` implementing `SemanticIndex.search(text, scope, c)`; `exact = True` for both.
> 2. Confirm `faiss.SearchParameters` and `faiss.IDSelectorBatch` usage in the installed faiss before coding; if unavailable, implement scoped search by computing inner products for scope rows (still exact) and note it.
> 3. Empty text → empty RankedList, no encoder call. Ranking key `(-round(score, 6), movie_id)`; evidence `semantic_rank`, `semantic_score`.
> 4. Raise `IndexUnavailable` / `ModelUnavailable` when artifacts or model cannot load.
> Do NOT add HNSW.
> **VERIFY:** `pytest -q tests/test_semantic_index.py` including FAISS == NumPy on 50 queries, full and scoped.

---

### T07 · Metadata and popularity — `cineverse/runtime/metadata_search.py` · [P0] · depends: T04
> **PROMPT**
> Goal: implement Recommendation Engine Spec §2 (11.3): `search` and `popularity`.
> Files you may touch: that file, `tests/test_metadata_search.py`.
> Requirements: sort keys, scores and evidence exactly as specified; scope respected; no genres and no terms → empty list.
> Do NOT use BM25 or any text-search library.
> **VERIFY:** `pytest -q tests/test_metadata_search.py`.

---

### T08 · Constraints, fusion, scoring — `cineverse/runtime/{constraints,fusion,scoring}.py` · [P0] · depends: T04
> **PROMPT**
> Goal: implement Recommendation Engine Spec §2 (11.4–11.5).
> Files you may touch: those three files and their tests.
> Requirements:
> 1. `mask`, `filter_list` (keep order, renumber, truncate to c); null ⇒ False.
> 2. `rrf(lists, k, z)` with z = 2/(k+1) passed in; `rank_key` helper.
> 3. `soft_score` with β, λ, μ from config; sums not fractions; unknown soft value counts as violation.
> 4. Test the hand-computed example (score 0.861166).
> Do NOT normalise RRF by the number of lists.
> **VERIFY:** `pytest -q tests/test_constraints.py tests/test_fusion.py tests/test_scoring.py`.

---

### T09 · Explanations — `cineverse/runtime/explain.py` · [P0] · depends: T06, T07, T08
> **PROMPT**
> Goal: implement Recommendation Engine Spec §2 (11.6) and §4 templates; `Recommendation` dataclass.
> Files you may touch: that file, `tests/test_explain.py`.
> Requirements: reasons only from evidence; template order; at most 4 reasons.
> Do NOT generate free text or call any model.
> **VERIFY:** `pytest -q tests/test_explain.py`.

---

### T10 · Baseline recommender — `cineverse/baseline/*` · [P0] · depends: T06–T09
> **PROMPT**
> Goal: implement Recommendation Engine Spec §5 (`BaselineSpec`, `recommend_baseline`) and `popularity.py` (B0).
> Files you may touch: `cineverse/baseline/*`, `tests/test_baseline.py`.
> Requirements: canonical-plan order (exhaustive search → filter_list → rrf → soft_score → top → explain); PopularityRank when no positives; never import the compiler except IR types.
> Do NOT optimize anything here; it is the reference.
> **VERIFY:** `pytest -q tests/test_baseline.py tests/test_layers.py`.

---

### PHASE 2 — Compiler front end

### T11 · Diagnostics, lexicon, lexer — `cineverse/compiler/{diagnostics,lexicon,lexer}.py` · [P0] · depends: T03
> **PROMPT**
> Goal: implement Frontend Spec §3 and §7.
> Files you may touch: those three files, `tests/test_lexer.py`.
> Requirements:
> 1. `TokenType`, `Token` exactly as §B.3; algorithm steps 1–7; precedence rule; spans index the original text.
> 2. All diagnostic codes and message templates from §B.7 in `diagnostics.py`.
> 3. ≥ 40 tests including every token sequence in the Example JSON `tokens` fields.
> Do NOT use spaCy/NLTK or any NLP library.
> **VERIFY:** `pytest -q tests/test_lexer.py`.

---

### T12 · AST and parser — `cineverse/compiler/{ast,parser}.py` · [P0] · depends: T11
> **PROMPT**
> Goal: implement Frontend Spec §4–§5 (grammar §B.4, AST §B.5).
> Files you may touch: those two files, `tests/test_parser.py`.
> Requirements: one procedure per non-terminal (Frontend Spec §4.1); optional SEP; LL(2) at HEDGE; OR in preferences and exclusions; panic-mode recovery with the synchronising set; P001/P002; `ast.to_dict`.
> Do NOT use a parser generator.
> **VERIFY:** `pytest -q tests/test_parser.py` (≥ 30 tests).

---

### T13 · Golden-file tooling — `tests/golden/*` · [P0] · depends: T12, T02
> **PROMPT**
> Goal: `tests/golden/regenerate.py --only tokens|ast|ir|program` writes golden files for every benchmark item; `tests/test_golden.py` compares.
> Files you may touch: `tests/golden/**`, `tests/test_golden.py`.
> Requirements: stable JSON (sorted keys, 2-space indent); report diffs clearly.
> Do NOT regenerate stages that do not exist yet (skip with a message).
> **VERIFY:** `python -m tests.golden.regenerate --only tokens --only ast && pytest -q tests/test_golden.py`.

---

### T14 · Domain registry — `cineverse/compiler/registry.py` · [P0] · depends: T04, T11
> **PROMPT**
> Goal: implement Frontend Spec §2: load `registry.yaml`, generate plurals, add catalogue stats and capabilities.
> Files you may touch: that file, `cineverse/config.py`, `tests/test_registry.py`.
> Requirements: runtime/language `available: false` in CORE; year domain from data; capabilities from artifacts presence.
> Do NOT hard-code fields in code.
> **VERIFY:** `pytest -q tests/test_registry.py`.

---

### T15 · Semantic analyser — `cineverse/compiler/semantic.py` · [P0] · depends: T12, T14
> **PROMPT**
> Goal: implement Frontend Spec §6 rules S1–S13 producing `SemanticResult` (§B.6).
> Files you may touch: that file, `tests/test_semantic.py`.
> Requirements: rule order as specified; diagnostics ordered by rule then span; ≥ 3 tests per rule; the invalid Example JSON items produce exactly their codes.
> Do NOT lower to IR here.
> **VERIFY:** `pytest -q tests/test_semantic.py`.

---

### T16 · IR — `cineverse/compiler/ir.py` · [P0] · depends: T15
> **PROMPT**
> Goal: implement IR and Execution Plan Spec §2 (§B.8): models, `lower`, validators V1–V5, `to_json`, `hash`, `from_json`, version handling.
> Files you may touch: that file, `tests/test_ir.py`.
> Requirements: frozen models; `semantic_text` rule; BETWEEN/DECADE lowering; spans kept but excluded from hash.
> Do NOT implement O1/O2 yet; V5 is asserted only after passes (skip until T22).
> **VERIFY:** `pytest -q tests/test_ir.py`.

---

### PHASE 3 — Back end and the preservation gate

### T17 · Planner — `cineverse/compiler/planner.py` · [P0] · depends: T16
> **PROMPT**
> Goal: implement IR and Execution Plan Spec §4–§5: the canonical template and `validate()`.
> Files you may touch: that file, `tests/test_planner.py`.
> Requirements: `pos_genres`/`pos_terms` definitions; PopularityRank iff no positives; nodes and ids exactly as specified.
> Do NOT prune anything (that is O3/O4).
> **VERIFY:** `pytest -q tests/test_planner.py`.

---

### T18 · Code generator — `cineverse/compiler/codegen.py` · [P0] · depends: T17
> **PROMPT**
> Goal: implement IR and Execution Plan Spec §6: topological order with id ties, SSA registers, printed form.
> Files you may touch: that file, `tests/test_codegen.py`.
> Requirements: the printed unoptimized program equals `program_unoptimized` in the Example JSON for every valid entry.
> Do NOT change the printed format.
> **VERIFY:** `pytest -q tests/test_codegen.py`.

---

### T19 · Executor and trace — `cineverse/runtime/{executor,trace}.py`, `trace_schema.json` · [P0] · depends: T18, T06–T09
> **PROMPT**
> Goal: implement IR and Execution Plan Spec §7 and Logging, Tracing and Observability §3.
> Files you may touch: those files, `tests/test_executor.py`, `tests/test_trace.py`.
> Requirements: validation (opcodes, def-before-use, SSA, types); dispatch table; timings; failure policy X201/X202/error; trace schema validation in tests.
> Do NOT import parser or semantic modules.
> **VERIFY:** `pytest -q tests/test_executor.py tests/test_trace.py tests/test_layers.py`.

---

### T20 · Driver and public API — `cineverse/compiler/driver.py`, `cineverse/__init__.py` · [P0] · depends: T19
> **PROMPT**
> Goal: `compile(text, optimize, rules)` returning `CompilationResult`; `recommend(text, optimize)`.
> Files you may touch: those two files, `cineverse/logging_setup.py`, `tests/test_driver.py`.
> Requirements: stop before planning on ERROR; per-stage timings; request id; logging per Logging §2. With no rules implemented yet, `optimize=True` behaves as `False`.
> **VERIFY:** `pytest -q tests/test_driver.py`; `python -c "from cineverse import recommend; c,e=recommend('no romance'); print(c.ok, len(e.results))"`.

---

### T21 · Behaviour preservation gate — `tests/test_preservation.py` · [P0] · depends: T20, T10, T02
> **PROMPT**
> Goal: Optimizer Spec §5.
> Files you may touch: `tests/test_preservation.py`, `benchmark/requests.jsonl` (baseline_spec fixes only, each listed in the report).
> Requirements: for every valid item, compiled-unoptimized results == `recommend_baseline(baseline_spec)` (ids, order, scores at 1e-6).
> Do NOT change compiler or runtime code to force a pass without reporting the root cause.
> **VERIFY:** `pytest -q tests/test_preservation.py` → 100% pass. **Gate: no optimizer task starts before this.**

---

### PHASE 4 — Optimizer

### T22 · O2 canonicalisation — `cineverse/compiler/passes.py` · [P0] · depends: T21
> **PROMPT**
> Goal: Optimizer Spec §3 (O2) with `Rule` object and `RuleApplication` logging.
> Files you may touch: `passes.py`, `tests/test_passes.py`, `compiler/driver.py` (wire passes only).
> Requirements: int fields only; sort/dedupe; idempotence property test; enable V5.
> **VERIFY:** `pytest -q tests/test_passes.py tests/test_ir.py`; EX23 and EX24 have equal `hash()`.

### T23 · O1 redundancy — `cineverse/compiler/passes.py` · [P0] · depends: T22
> **PROMPT**
> Goal: Optimizer Spec §3 (O1 a–c) including the negative test (two soft bounds not merged).
> Files you may touch: `passes.py`, `tests/test_passes.py`.
> **VERIFY:** `pytest -q tests/test_passes.py`; EX25 shows the O1 application.

### T24 · O3 dead operators — `cineverse/compiler/optimizer.py` · [P0] · depends: T23
> **PROMPT**
> Goal: Optimizer Spec §4 (O3) with `Capabilities`.
> Files you may touch: `optimizer.py`, `tests/test_optimizer.py`, `compiler/driver.py` (wire optimizer only).
> **VERIFY:** `pytest -q tests/test_optimizer.py`; EX03, EX12, EX22 show O3 removing both searches.

### T25 · O4 pushdown + equivalence — `optimizer.py`, `equivalence.py` · [P0] · depends: T24
> **PROMPT**
> Goal: Optimizer Spec §4 (O4), §6 (equivalence harness), §7 (property tests).
> Files you may touch: `cineverse/compiler/optimizer.py`, `cineverse/compiler/equivalence.py`, `tests/test_optimizer.py`, `tests/test_equivalence.py`, `tests/test_properties.py`.
> Requirements: shared Mask; truncation-only pushdown when no hard predicates; refuse when `exact_search` is false; property test with 200 random predicate sets.
> Do NOT approximate, cache results, or change scoring.
> **VERIFY:** `pytest -q tests/test_equivalence.py tests/test_properties.py` → 100%; optimized programs equal `program_optimized` in the Example JSON.

---

### PHASE 5 — Product

### T26 · Tuning on dev — `cineverse/eval/tune.py`, `config/runtime.yaml` · [P0] · depends: T25, H2 (dev judgments)
> **PROMPT**
> Goal: Evaluation Plan §8 step 1 grid search on the dev split only; write chosen β, λ, μ, C to `runtime.yaml`; record in the decision log.
> Files you may touch: `tune.py`, `config/runtime.yaml`, `docs/CineVerse_Project_Control.md` (decision log row).
> Do NOT read any test-split judgment.
> **VERIFY:** `python -m cineverse.eval.tune --split dev` prints the grid and the chosen values.

### T27 · Example conformance — `tests/test_examples.py` · [P0] · depends: T25
> **PROMPT**
> Goal: assert every Example JSON entry: tokens, diagnostics, IR (no spans), rules fired, both programs, result properties (executable assertions for each listed property).
> Files you may touch: `tests/test_examples.py`.
> **VERIFY:** `pytest -q tests/test_examples.py` → 25 passed.

### T28 · Streamlit app — `app/streamlit_app.py` · [P0] · depends: T27
> **PROMPT**
> Goal: implement UI/UX and API Specification §2 exactly (layout, components, Compiler view tabs, toggle, caching).
> Files you may touch: `app/streamlit_app.py`.
> Requirements: confirm `st.cache_resource`, `st.tabs`, `st.toggle`, `st.graphviz_chart` in the installed Streamlit first; never compute scores in the UI.
> **VERIFY:** `streamlit run app/streamlit_app.py`; manually pass UI/UX Spec §6 checklist; screenshot each tab into `docs/status/T28/`.

---

### PHASE 6 — Evidence and release

### T29 · Evaluation — `cineverse/eval/*` · [P0] · depends: T28, H1, H2
> **PROMPT**
> Goal: implement Evaluation and Benchmarking Plan §3–§9: compiler metrics, systems B0/B1/B2/Baseline/Compiled/Compiled+O, metrics with bootstrap CIs, latency, `run_all` and `run_manifest.json`.
> Files you may touch: `cineverse/eval/*`, `tests/test_eval_metrics.py`.
> Requirements: refuse to run if the test split hash changed after freeze; unit-test NDCG/MRR/precision on hand examples.
> Do NOT type any number into documents.
> **VERIFY:** `python -m cineverse.eval.run_all` writes every file listed in Database and Data Schemas §7.

### T30 · Release — docs and checks · [P0] · depends: T29
> **PROMPT**
> Goal: README, CHANGELOG, report tables from `results/`, clean-install check, release per Deployment and Runbook §7.
> Files you may touch: `README.md`, `docs/CHANGELOG.md`, `docs/status/*`, report source.
> **VERIFY:** Testing Plan §9 and Runbook §4 checklists all ticked; tag `v1.0`.

---

### OPTIONAL (only after T30)

### T31 · MMR — `cineverse/runtime/diversity.py` · [P1] · depends: T30
> **PROMPT** Implement Engine Spec 11.7; set `mmr_available`; planner emits Diversify; codegen emits `MMR`; EX16 then shows no S105 and an `%d = MMR` line. Add O5 only if specified first in the Optimizer Spec. **VERIFY:** tests for λ = 1 equals non-diverse ranking; equivalence still 100%.

### T32 · TMDB enrichment — `cineverse/data/enrich_tmdb.py` · [P1] · depends: T30
> **PROMPT** Implement Dataset Spec §7. Read the live TMDB API docs before writing the client; key from `.env` only; registry marks fields available only at ≥ 90% coverage. **VERIFY:** EX07 then compiles a runtime constraint and S105 disappears.

### T33 · FastAPI — `api/main.py` · [P1] · depends: T30
> **PROMPT** Implement UI/UX and API Spec §4; bind 127.0.0.1. **VERIFY:** `pytest -q tests/test_api.py` with FastAPI TestClient.

### T34 · Feedback — `storage/feedback.py` · [P1] · depends: T30
> **PROMPT** Implement Database and Data Schemas §8; thumbs up/down in the UI. **VERIFY:** `pytest -q tests/test_feedback.py`.

---

## §E. Build Order

| Window | Tasks | Outcome |
|---|---|---|
| Week 1 | T01–T04 | Specs signed off; environment; catalogue |
| Week 2 | T05–T10 | Runtime operators; baseline |
| Week 3 | T11–T13 | Lexer, parser, golden files |
| Week 4 | T14–T16 | Registry, semantics, IR |
| Week 5 | T17–T21 | Planner, codegen, executor, driver; **preservation gate** |
| Week 6 | T22–T25 | O2, O1, O3, O4; **equivalence gate** |
| Week 7 | T26–T28 | Tuning, example conformance, Streamlit app |
| Week 8 | T29–T30 | Evaluation, report, release |
| After | T31–T34 | Optional features |

Adjust week boundaries to the course calendar in Project Control §3; never reorder dependencies.

## §F. Final Acceptance

- [ ] `pytest -q` green on a clean clone (≥ 1 Windows machine).
- [ ] Preservation 100%; equivalence 100% (each rule and all rules).
- [ ] All 25 Example JSON entries conform.
- [ ] Zero hard-constraint violations on the benchmark.
- [ ] Layer test green; ruff clean; mypy clean for `cineverse/compiler`.
- [ ] `python -m cineverse.eval.run_all` regenerates every results file.
- [ ] Streamlit demo script (Runbook §6) runs offline.
- [ ] Report numbers match `results/`.
