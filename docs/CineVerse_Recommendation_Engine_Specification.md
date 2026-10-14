# CineVerse — Recommendation Engine Specification
**Recommendation Engine Specification · v1.0**

Team 14 (Santhoshraja S, Siddharth P, Keshore G) · 2026-10-14 · Status: Draft for team review

---

> **Normative.** Defines the runtime operators the compiled program calls: catalogue access, semantic search, metadata and popularity ranking, hard constraints, RRF fusion, soft scoring, explanations, optional MMR, and the baseline recommender. The engine is the compiler's target machine: it never sees English, only instructions.

## Contents
1. Role and Principles · 2. Runtime Types and Operators · 3. Scoring Walkthrough · 4. Explanation Templates · 5. Baseline Recommender · 6. Configuration · 7. Test Obligations

## 1. Role and Principles
- Executes instructions produced by the compiler; preserves the hard/soft split exactly.
- Deterministic: every ordering uses `(-round(score, 6), movie_id)` unless a sort key is defined explicitly below.
- Exact search only in CORE (makes optimizer rule O4 provably safe).
- Evidence-first: every operator records why each movie it outputs is there.

## 2. Runtime Types and Operators
### 11.1 Types

```python
@dataclass(frozen=True)
class RankedList:
    ids: tuple[int, ...]            # rank = index + 1
    scores: tuple[float, ...]
    source: str                     # "semantic" | "metadata" | "rrf" | "soft" | "mmr" | "topk"
    evidence: dict[int, dict]       # per-movie evidence accumulated for explanations
```

Every ranking sorts by `(-round(score, 6), movie_id)`.

### 11.2 Semantic search (`semantic_index.py`, `embeddings.py`)
Model `sentence-transformers/all-MiniLM-L6-v2`, `normalize_embeddings=True`. Backends: `FaissFlatIndex` (`IndexIDMap(IndexFlatIP)`; scope via `faiss.SearchParameters(sel=faiss.IDSelectorBatch(ids))`) and `NumpyIndex` (matrix product on the scope rows). Empty `text` → empty list (no encoder call). Evidence: `{"semantic_rank", "semantic_score"}`.

### 11.3 Metadata search (`metadata_search.py`)
Score key per movie in scope: `(genre_matches, tag_term_matches)`; keep movies with any match; sort by `(-genre_matches, -tag_term_matches, -bayes, movie_id)`; score = `genre_matches + 0.5·tag_term_matches`. Tag term match = descriptor appears as a word or phrase inside any tag. Evidence: matched genres and tags, metadata rank.
`popularity(catalog, scope, c)`: rank the scope by `(-round(bayes, 6), movie_id)`; score = `bayes`. Evidence: popularity rank, Bayesian rating, votes.

### 11.4 Fusion (`fusion.py`)
`RRF(d) = Σ_r 1/(k + rank_r(d))`, k = 60. Output score = `RRF(d) / Z` with **Z = 2/(k+1)** (constant, independent of how many lists ran).

### 11.5 Constraints and soft scoring (`constraints.py`, `scoring.py`)
Hard predicate evaluation: `HAS`/`NOT_HAS` on genres; `<=`/`>=`/`<`/`>` on numbers; null ⇒ False.
`Score(d) = RRF(d)/Z + β·Σ_{p∈P+} m(p,d) − λ·Σ_{p∈P−} m(p,d) − μ·Σ_{c∈C_soft} v(c,d)`; m = 1 if genre in d.genres or descriptor matches a tag; v = 1 if soft constraint violated or value unknown. Defaults (`config/runtime.yaml`): β = 0.10, λ = 0.30, μ = 0.20, candidate_budget C = 200, rrf_k = 60. Tune only on the dev split, then freeze.

### 11.6 Explanations (`explain.py`)
Templates, each emitted only if its evidence exists: genres matched; tags matched (with the request words they matched); semantic rank; metadata rank; each hard constraint with the movie's actual value; soft penalties applied. Output `Recommendation(movie_id, title, year, genres, score, reasons: list[str], evidence: dict)`.

### 11.7 Optional MMR (`diversity.py`)
`MMR(d) = λ·Rel(d) − (1−λ)·max_{s∈S} cos(d, s)` over movie embeddings, greedy to n.

### 2.1 Operator function signatures
```python
# runtime/catalog.py
class Catalog:
    @classmethod
    def load(cls, path: Path) -> "Catalog"
    def all_ids(self) -> np.ndarray                      # sorted int64
    def get(self, movie_id: int) -> MovieRecord
    def column(self, name: str) -> np.ndarray            # aligned with all_ids()

# runtime/semantic_index.py
class SemanticIndex(Protocol):
    exact: bool
    def search(self, text: str, scope: np.ndarray | None, c: int) -> RankedList

# runtime/metadata_search.py
def search(catalog: Catalog, genres: list[str], terms: list[str], scope: np.ndarray, c: int) -> RankedList
def popularity(catalog: Catalog, scope: np.ndarray, c: int) -> RankedList

# runtime/constraints.py
def mask(catalog: Catalog, scope: np.ndarray, preds: list[Constraint]) -> np.ndarray
def filter_list(catalog: Catalog, rl: RankedList, preds: list[Constraint], c: int) -> RankedList

# runtime/fusion.py
def rrf(lists: list[RankedList], k: int, z: float) -> RankedList

# runtime/scoring.py
def soft_score(catalog: Catalog, rl: RankedList, prefs: list[Preference],
               soft: list[Constraint], cfg: SoftConfig) -> RankedList

# runtime/explain.py
def explain(catalog: Catalog, rl: RankedList, ir: CompiledQuery) -> list[Recommendation]

# runtime/diversity.py (OPTIONAL)
def mmr(rl: RankedList, embeddings: np.ndarray, lam: float, n: int) -> RankedList
```

## 3. Scoring Walkthrough
For a movie d that is rank 2 in semantic search and rank 5 in metadata search, k = 60:

| Quantity | Value |
|---|---|
| RRF(d) | 1/62 + 1/65 = 0.016129 + 0.015385 = 0.031514 |
| Z | 2/61 = 0.032787 |
| RRF(d)/Z | 0.961166 |
| Positive matches (Sci-Fi, Mystery) | +0.10 × 2 = +0.20 |
| Negative soft match (Romance) | −0.30 × 1 = −0.30 |
| Soft constraint violations | 0 |
| Score(d) | 0.861166 (after rounding to 6 decimals) |

A movie appearing only in one list at rank 1 gets RRF/Z = (1/61)/(2/61) = 0.5 before soft terms.

## 4. Explanation Templates
| Evidence | Template |
|---|---|
| genres matched | "Genres {g1} and {g2} match your request" |
| tags matched | "Tagged '{tag}', matching '{term}'" |
| semantic rank | "Close in meaning to '{semantic_text}' (rank {r})" |
| metadata rank | "Matches your genres and keywords (rank {r})" |
| popularity rank | "Highly rated: {rating:.1f}★ from {votes} ratings" |
| hard bound satisfied | "Released {year} ({human bound})", "Rated {rating:.1f}★ (at least {v})" |
| hard exclusion satisfied | "Not {genre}" |
| soft penalty applied | "Includes {genre}, which you wanted little of" |
| soft constraint violated | "Released {year}, earlier than you preferred" |
At most 4 reasons per movie, in the order above; the trace keeps all evidence.

## 5. Baseline Recommender
```python
@dataclass
class BaselineSpec:
    semantic_text: str; pos_genres: list[str]; pos_terms: list[str]; neg_soft: list[Preference]
    hard: list[Constraint]; soft_constraints: list[Constraint]; limit: int
def recommend_baseline(spec: BaselineSpec, ctx: RuntimeContext) -> list[Recommendation]
```

Calls runtime functions directly in the canonical-plan order (exhaustive search → filter_list → rrf → soft_score → top → explain). It never imports `cineverse.compiler`.

## 6. Configuration
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

## 7. Test Obligations
| Module | Tests |
|---|---|
| `semantic_index.py` | FAISS == NumPy on 50 queries, full and scoped; empty text → empty list without encoder call; self-retrieval |
| `metadata_search.py` | Sort key order; tag phrase matching; no-match exclusion; popularity order and ties |
| `constraints.py` | Each op; null ⇒ False; mask == filter_list on random lists |
| `fusion.py` | Hand-computed example (§3); constant Z; single-list case |
| `scoring.py` | β, λ, μ arithmetic; unknown soft value counts as violation; rounding |
| `explain.py` | Every reason maps to evidence; no reason without evidence; ≤ 4 reasons |
| `baseline.py` | Never imports the compiler; returns results for 10 hand specs |
