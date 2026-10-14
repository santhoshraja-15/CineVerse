# CineVerse — Technical Deep-Dive
**Technical Deep-Dive · v1.0**

Team 14 (Santhoshraja S, Siddharth P, Keshore G) · 2026-10-14 · Status: Draft for team review

---

> **Alignment.** Data models in this document are copied from the normative specifications (Frontend, IR and Execution Plan, Optimizer, Recommendation Engine, Database and Data Schemas). If this document and a normative specification ever disagree, the specification wins.

## Contents
1. The Unifying Thesis
2. System Topology
3. Lexer — words become typed tokens
4. Parser and AST — tokens become structure
5. Domain Registry — the symbol table
6. Semantic Analyser and Diagnostics — structure becomes checked meaning
7. IR and IR Passes — meaning fixed once
8. Logical Planner — meaning becomes a plan
9. Plan Optimizer — cheaper, never different
10. Code Generator and Executor — the plan becomes a running program
11. Retrieval Operators — semantic, metadata, popularity
12. Fusion, Constraints and Soft Scoring — ranking with honest rules
13. Explanations and Trace — every result traced to the words that caused it
14. Streamlit App — the compiler, visible
15. End-to-End Walkthrough — A Day in the Life
16. Build Priority — What Ships First

## 1. The Unifying Thesis

**A movie request is a program, and its meaning is fixed exactly once.** The front end turns English into a checked meaning; the IR records that meaning in a canonical, hashable form; everything after the IR is either a transformation proven not to change that meaning (passes and plan rules) or the execution of it (runtime). Three consequences follow, and the whole architecture exists to deliver them:

1. **Honesty.** A condition is either enforced (hard), weighed (soft) or reported unsupported (diagnostic). Nothing is silently dropped or silently "satisfied".
2. **Provable optimization.** Because meaning is defined on the IR, an optimized plan can be tested against the unoptimized one, and the unoptimized one against a hand-wired baseline.
3. **Traceability.** Spans flow from tokens to AST to IR to plan to evidence, so every reason shown to the user points back to words in the request.

## 2. System Topology

```
text
 │  Lexer ──────────────▶ Token[]                 (compiler/lexer.py)
 │  Parser ─────────────▶ RequestNode (AST)       (compiler/parser.py, ast.py)
 │  Semantic analyser ──▶ SemanticResult           (compiler/semantic.py) ◀── Domain registry (registry.py)
 │  Lowering ───────────▶ CompiledQuery (IR)       (compiler/ir.py)
 │  IR passes O2, O1 ───▶ CompiledQuery            (compiler/passes.py)
 │  Planner ────────────▶ LogicalPlan              (compiler/planner.py)
 │  Optimizer O3, O4 ───▶ LogicalPlan              (compiler/optimizer.py)
 │  Code generator ─────▶ Instruction[] (SSA)      (compiler/codegen.py)
 ▼  Executor ───────────▶ ExecutionResult          (runtime/executor.py)
       └─ dispatches to runtime operators: catalog, semantic_index, metadata_search,
          constraints, fusion, scoring, explain   (runtime/*.py)
```

### 2.1 Cross-cutting components
| Component | Touches | Role |
|---|---|---|
| Diagnostics (`compiler/diagnostics.py`) | All compiler stages, executor | Values, not exceptions; ERROR stops before planning |
| Trace (`runtime/trace.py`) | Every stage | One JSON per request; powers UI, tests, debugging |
| Config (`config/*.yaml`) | Registry, runtime | No magic numbers in code |
| Driver (`compiler/driver.py`) | Compiler stages | Orchestrates, times each stage, returns `CompilationResult` |

**Layer rule:** `cineverse.compiler` never imports `cineverse.runtime` internals; `cineverse.runtime` never imports the parser. They meet at the IR, the plan and the instruction list (Layer Architecture Requirements).

## 3. Lexer — words become typed tokens

#### The problem it owns
English is a stream of characters; nothing downstream can reason about it until words become typed units. Negation ("not too") and numbers must survive, multi-word phrases ("science fiction") must become one unit, and every unit must remember where it came from.

#### How it works
1. Reject empty or over-long input (S113).
2. Normalise (lower-case, unify dashes and quotes) without changing length, so spans map 1:1 to the original.
3. Scan words; try 4-, 3-, 2-, 1-word phrase matches against the lexicon (longest match), with precedence genre alias > NEG_SOFT > closed tables > DESCRIPTOR > FILLER > WORD.
4. Recognise numbers, number words and decades.
5. Remove FILLER before parsing (kept in trace).

#### Data model
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

#### Stack mapping
Python `re` for scanning; dict/trie lookup built from `registry.yaml` aliases and `lexicon.py` tables. No NLP library, so behaviour is fully deterministic and testable.

#### Why it lands
"not too violent" becomes `NEG_SOFT DESCRIPTOR`, never `NEG_HARD`; "sci-fi" becomes one `GENRE` token with value `Sci-Fi`; every later error message can underline exactly the words that caused it.

## 4. Parser and AST — tokens become structure

#### The problem it owns
A flat token list does not say which words belong together: does "little" apply to "romance" or to "sci-fi"? Is 2010 a year bound or a result count?

#### How it works
Recursive descent over the grammar below, one function per non-terminal. LL(1) everywhere except after HEDGE, where a second token chooses between a hedged constraint, a hedged exclusion and a hedged preference. Separators are optional between clauses. Panic-mode recovery (skip to next SEP, emit P001) guarantees an AST for every input.

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

#### Data model
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

#### Stack mapping
Pure Python, frozen dataclasses; `ast.to_dict()` for golden files and the UI. No parser generator: the grammar is small, and hand-written descent shows FIRST sets, lookahead and recovery explicitly.

#### Why it lands
The AST makes the request's structure inspectable and testable with golden files, and it is where "only comedy or drama" becomes visibly different from "only animated comedies".

## 5. Domain Registry — the symbol table

#### The problem it owns
The compiler must know what names exist (genres, fields, units), their types, operators and whether the data can actually verify them. If this knowledge is scattered, the compiler will eventually promise a filter the data cannot honour.

#### How it works
Loaded once from `config/registry.yaml`, then completed from catalogue statistics: year domain, per-field coverage, channel capabilities (index present, MMR built). Fields absent from MovieLens (`runtime`, `language`) are declared but `available: false`.

#### Data model
```yaml
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

#### Stack mapping
PyYAML for the file; pandas statistics from `catalog.parquet`; a frozen `DomainRegistry` object passed to lexer and semantic analyser.

#### Why it lands
"Under 2 hours" is understood (unit → runtime, 2 h → 120 min) and then refused honestly with S105, instead of being silently ignored or silently "satisfied".

## 6. Semantic Analyser and Diagnostics — structure becomes checked meaning

#### The problem it owns
A grammatical request can still be meaningless or impossible: "rated above 9", "after 2015 before 2000", "only horror and no horror". Hardness must also be decided here: "no romance" and "little romance" parse alike but mean different things.

#### How it works
One walk over the AST applying S1–S13 in order: name resolution, field inference, type and range checks, unit conversion, capability check, strictness/polarity assignment, verifiability, contradiction, empty range, precedence, non-emptiness, strict alternatives. Output: annotations per node plus diagnostics. Any ERROR stops the driver.

#### Data model
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

| ID | Rule |
|---|---|
| S1 | Resolve GenreTerm via aliases/plurals to canonical genres. A WORD that is not a genre stays a DescriptorTerm (S101 INFO only if it looks like a genre, edit distance ≤ 2) |
| S2 | Infer missing field of a ConstraintClause: unit → field via `units`; else integer value in year domain or DECADE → `year`; else S102 ERROR |
| S3 | Type check: op ∈ field.ops (after mapping `<`,`>` to the field's type); value type matches; else S103 ERROR |
| S4 | Range check against field domain → S104 ERROR. Limit outside 1–50 → clamp + S109 WARNING. Missing limit number → default |
| S5 | Unit conversion: value × factor; S112 INFO when factor ≠ 1 |
| S6 | Capability: field `available: false` → S105 WARNING, annotation `applied=False` |
| S7 | Strictness/polarity: PreferenceClause NONE/HEDGE → soft, polarity +1 (genres and descriptors); STRICT + genre → hard `genre HAS g`; STRICT + descriptor → soft (+S106); ExclusionClause HARD (not hedged) + genre → hard `NOT_HAS`; HARD + descriptor → soft polarity −1 + S106; SOFT, or hedged HARD → soft polarity −1; ConstraintClause hedged → soft, else hard; BETWEEN → two annotations (≥ low, ≤ high); DECADE → (≥ start, ≤ end) |
| S8 | (part of S7) hard exclusion of a descriptor is unverifiable → soft, S106 WARNING |
| S9 | Same genre hard HAS and hard NOT_HAS → S107 ERROR (spans of both) |
| S10 | Hard bounds on one field with empty intersection (after converting `<`/`>` on int fields to closed bounds) → S108 ERROR |
| S11 | Soft positive genre that is also hard NOT_HAS → soft dropped, S110 WARNING; soft negative genre that is hard HAS → soft dropped, S110 |
| S12 | No applied preference, constraint or exclusion → S111 ERROR |
| S13 | STRICT clause whose genres are joined by OR ("only comedy or drama") → all its genres soft, S114 WARNING. STRICT with several genres and no OR ("only animated comedies") → one hard HAS per genre |

Diagnostic codes:

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

#### Stack mapping
Pure Python over the AST and registry; diagnostics are frozen dataclasses rendered by the UI with span highlights.

#### Why it lands
The examiner can type a contradiction and watch the compiler stop with both clauses underlined, before any movie is touched.

## 7. IR and IR Passes — meaning fixed once

#### The problem it owns
Different wordings of the same request must have one representation, and that representation must be independent of both the parser and the runtime so either can change without breaking the other.

#### How it works
Lowering maps annotations to IR elements (soft → `Preference` or soft `Constraint`; hard → `Constraint`; BETWEEN and decades → two bounds). `semantic_text` collects only positive terms, so negated words are never embedded. Passes run in order O2 (canonicalise: integer `>`/`<` → `>=`/`<=`, sort, dedupe) then O1 (remove duplicates, keep the tighter of two hard bounds, drop soft bounds implied by hard ones).

#### Data model
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

#### Stack mapping
Pydantic v2 models with validators V1–V5; `to_json()` with sorted keys; `hash()` = SHA-256 over canonical JSON without source, diagnostics and spans.

#### Why it lands
"comedies made after 2010" and "comedy from 2011" get the same IR hash: the compiler can prove two sentences mean the same thing.

## 8. Logical Planner — meaning becomes a plan

#### The problem it owns
The IR says what is wanted, not how to compute it. The planner must produce an executable dataflow that is obviously correct, even if slow, so it can serve as the reference for optimization.

#### How it works
One fixed template for every IR: exhaustive semantic and metadata searches over the whole catalogue, a FilterList per source applying hard constraints and truncating to C, Fuse, SoftScore, optional Diversify, TopK, Explain. If the request has no positive preference, PopularityRank is added as a third source. The planner never prunes; that is the optimizer's job.

#### Data model
```python
@dataclass
class PlanNode:
    id: str; op: str; args: dict; inputs: list[str]; out_type: Literal["MovieSet", "RankedList", "Results"]
@dataclass
class LogicalPlan:
    nodes: dict[str, PlanNode]; sink: str
    def validate(self) -> list[str]   # acyclic, inputs exist, types match op signature, single sink
```

#### Stack mapping
Python dataclasses; `LogicalPlan.validate()` checks acyclicity, inputs, operator signatures and single sink.

#### Why it lands
The canonical plan is the executable definition of the IR's meaning. Every optimization is judged against it.

## 9. Plan Optimizer — cheaper, never different

#### The problem it owns
The canonical plan scores every movie twice and filters afterwards. It should do less work without ever returning anything different.

#### How it works
Rules are `(id, precondition, apply)`; each application is logged with before/after. O3 deletes sources whose output is provably empty (the two searches when the request has no positive terms) and unused nodes. O4 pushes the hard filter (and the truncation) into the sources as one shared Mask, valid only for exact search with deterministic tie-breaking. Re-ranking (SOFT, MMR) is never an optimization.

#### Data model
```python
@dataclass
class RuleApplication:
    rule: Literal["O1", "O2", "O3", "O4"]
    level: Literal["ir", "plan"]
    detail: str                 # e.g. "year > 2010 -> year >= 2011"
    before: dict                # IR or plan snapshot (to_dict)
    after: dict
RuleLog = list[RuleApplication]

@dataclass(frozen=True)
class Capabilities:
    exact_search: bool          # True for faiss_flat and numpy backends
    semantic_available: bool
    mmr_available: bool
```

#### Stack mapping
Pure Python over `LogicalPlan`; `compiler/equivalence.py` runs both plans and compares ids, scores (rounded 1e-6), constraint outcomes and diagnostics.

#### Why it lands
The optimizer toggle in the demo returns the same five movies with a smaller search time, and the test suite proves it for every benchmark request.

## 10. Code Generator and Executor — the plan becomes a running program

#### The problem it owns
A DAG is hard to show, diff and step through. A linear program in SSA form can be printed, validated and executed one instruction at a time with timings.

#### How it works
Topological order with ties by node id; one register per node. The executor validates opcodes, def-before-use, single assignment and operand types, then dispatches each opcode to a runtime function, timing it and recording output size and a sample. Failure policy: semantic search unavailable → X201 and an empty list; empty eligible set → X202; anything else → ERROR and partial trace.

#### Data model
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

#### Stack mapping
Python; dispatch table `dict[str, Callable]`; `time.perf_counter_ns` for timings.

#### Why it lands
The examiner sees a real target program, can compare it before and after optimization, and can see where the time went.

## 11. Retrieval Operators — semantic, metadata, popularity

#### The problem it owns
Find candidates that match the meaning of the request (semantic), its explicit genres and words (metadata), or, when it has no positive wish at all, simply good movies (popularity).

#### How it works
- **Semantic:** encode `semantic_text` with all-MiniLM-L6-v2 (normalised), exact inner-product search over movie vectors; scope restricts the search to eligible ids.
- **Metadata:** count genre matches and descriptor-in-tag matches; rank by genre matches, tag matches, Bayesian rating, id.
- **Popularity:** rank scope by Bayesian rating, then id.
All rankings sort by `(-round(score, 6), movie_id)`.

#### Data model
```python
@dataclass(frozen=True)
class RankedList:
    ids: tuple[int, ...]            # rank = index + 1
    scores: tuple[float, ...]
    source: str                     # "semantic" | "metadata" | "rrf" | "soft" | "mmr" | "topk"
    evidence: dict[int, dict]       # per-movie evidence accumulated for explanations
```

#### Stack mapping
sentence-transformers for encoding; faiss-cpu `IndexIDMap(IndexFlatIP)` with `IDSelectorBatch` for scope; NumPy backend with the same interface; pandas for metadata.

#### Why it lands
Exact search plus deterministic ties is what makes O4 provably safe, and the NumPy backend removes the main installation risk.

## 12. Fusion, Constraints and Soft Scoring — ranking with honest rules

#### The problem it owns
Combine sources with incomparable scores, remove what must be removed, and weigh what should only be weighed.

#### How it works
```
RRF(d)   = Σ_r 1 / (k + rank_r(d)),  k = 60
Z        = 2 / (k + 1)          (constant: makes O3 exact)
Score(d) = RRF(d)/Z + β·Σ_{p∈P+} m(p,d) − λ·Σ_{p∈P−} m(p,d) − μ·Σ_{c∈C_soft} v(c,d)
β = 0.10, λ = 0.30, μ = 0.20   (tuned on dev split only)
```
Hard predicates act only in MASK/FILTER_LIST; unknown values fail them. Soft conditions act only in SOFT; unknown values count as violations.

#### Data model
```yaml
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

#### Stack mapping
NumPy/pandas vectorised predicate evaluation; pure Python fusion and scoring over at most 3 × C candidates.

#### Why it lands
"No romance" removes romance; "little romance" sinks it; the constant Z keeps scores identical when O3 removes an empty source.

## 13. Explanations and Trace — every result traced to the words that caused it

#### The problem it owns
Users and examiners need to know why each movie appeared, and developers need to know what every stage produced.

#### How it works
Operators accumulate per-movie evidence (ranks, matched genres, matched tags, constraint values, penalties). `explain.py` fills fixed templates only from that evidence. `trace.py` writes one JSON document per request with every stage's output and timings.

#### Data model
```python
@dataclass(frozen=True)
class Recommendation:
    movie_id: int; title: str; year: int | None; genres: tuple[str, ...]
    score: float; reasons: tuple[str, ...]; evidence: dict
```
Trace schema: see Logging, Tracing and Observability §3.

#### Stack mapping
Python string templates; `json` + `jsonschema` (test-only) for trace validation.

#### Why it lands
A reason without evidence cannot be produced, so explanations are faithful by construction and testable clause by clause.

## 14. Streamlit App — the compiler, visible

#### The problem it owns
A compiler's work is invisible unless it is shown; a recommender is useless unless it is pleasant to use.

#### How it works
Request box with example chips; result cards; diagnostics banner with highlighted spans; Compiler view tabs (Tokens, AST, Semantic, IR, Plan, Program, Timings, Trace); optimizer toggle; cached model and index (`st.cache_resource`).

#### Data model
None of its own. It renders `CompilationResult` and `ExecutionResult`.

#### Stack mapping
Streamlit; `st.tabs`, `st.json`, `st.code`, `st.dataframe`; Graphviz text for plans via `st.graphviz_chart`.

#### Why it lands
The viva becomes a walkthrough: type, look at each tab, flip the optimizer, repeat with a contradiction.

## 15. End-to-End Walkthrough — A Day in the Life

Asha types **"thoughtful sci-fi mystery after 2010, little romance, top 5"**.

1. **Lexer:** `DESCRIPTOR(thoughtful) GENRE(Sci-Fi) GENRE(Mystery) CMP(>) NUMBER(2010) SEP NEG_SOFT GENRE(Romance) SEP LIMIT NUMBER(5)`, each with spans.
2. **Parser:** PreferenceClause[thoughtful, Sci-Fi, Mystery] · ConstraintClause(>, 2010) · ExclusionClause(SOFT, Romance) · LimitClause(5).
3. **Semantics:** 2010 has no field and no unit, but lies in the year domain → `year` (S2); unhedged → hard; "little" → soft −1 Romance; no errors.
4. **IR + passes:** O2 rewrites `year > 2010` to `year >= 2011`; `semantic_text = "thoughtful science fiction mystery"`.
5. **Planner:** semantic and metadata searches over all N movies, FilterList(year >= 2011, C=200) each, RRF, SOFT, TOPK 5, EXPLAIN.
6. **Optimizer:** O3 not applicable; O4 inserts one MASK and searches only eligible movies with c=200.
7. **Codegen:**
```
%s0 = SCAN
%m1 = MASK %s0, [year >= 2011]
%a1 = SEM_SEARCH "thoughtful science fiction mystery", %m1, c=200
%b1 = META_SEARCH genres=[Mystery, Sci-Fi], terms=[thoughtful], %m1, c=200
%f = RRF %a1, %b1, k=60
%r = SOFT %f, prefs=[genre:Mystery+, genre:Romance-, genre:Sci-Fi+, text:thoughtful+], soft=[]
%t = TOPK %r, n=5
%x = EXPLAIN %t
RET %x
```
8. **Executor:** MASK keeps movies from 2011 onwards; both searches run on that scope; RRF; Romance movies lose 0.30; top 5; explanations.
9. **UI:** five cards, e.g. "Genres Sci-Fi and Mystery match; tags 'thought-provoking' matches 'thoughtful'; released 2014 (from 2011); semantic rank 2". The Compiler view shows every step; turning the optimizer off gives the same five movies.

## 16. Build Priority — What Ships First

| Tier | Components | Rationale |
|---|---|---|
| P0 foundation | Catalogue, runtime operators, baseline | Gives the compiler a target and a reference |
| P0 compiler | Lexer, parser, AST, registry, semantics, diagnostics, IR, planner, codegen, executor, trace | The course deliverable |
| P0 gate | Preservation test | Proves the compiler did not change the recommender |
| P0 optimizer | O2, O1, O3, O4 + equivalence | The optimization contribution |
| P0 product | Explanations, Streamlit app, evaluation | Demo and evidence |
| P1 | MMR, TMDB enrichment, FastAPI, SQLite feedback, HNSW scale run | Only after all P0 tests pass |
| P2 | Title references, multi-turn IR patches, multilingual | Future work |
