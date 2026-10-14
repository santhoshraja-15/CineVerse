# CineVerse — Database and Data Schemas
**Database and Data Schemas · v1.0**

Team 14 (Santhoshraja S, Siddharth P, Keshore G) · 2026-10-14 · Status: Draft for team review

---

> **Normative.** CineVerse has no database server. All persistent data is files: Parquet, NumPy, FAISS, JSON, JSONL, CSV and YAML, plus one OPTIONAL SQLite file for feedback. This document fixes every stored format.

## Contents
1. Storage Map · 2. Catalogue (Parquet) · 3. Artifacts and Manifest · 4. Configuration Files · 5. Benchmark and Judgments · 6. Trace · 7. Results · 8. Optional SQLite Feedback · 9. Schema Versioning

## 1. Storage Map
| Path | Format | Schema § | Committed to Git |
|---|---|---|---|
| `data/raw/ml-latest-small/*.csv` | CSV | Dataset Spec §1 | No |
| `data/processed/catalog.parquet` | Parquet | §2 | No |
| `artifacts/embeddings.npy`, `ids.npy`, `faiss.index` | NumPy / FAISS | §3 | No |
| `artifacts/manifest.json` | JSON | §3 | No (copied into results) |
| `config/registry.yaml`, `config/runtime.yaml` | YAML | §4 | Yes |
| `benchmark/requests.jsonl` | JSONL | §5 | Yes |
| `benchmark/judgments.csv` | CSV | §5 | Yes |
| `traces/<request_id>.json` | JSON | §6 | No |
| `results/*.csv`, `results/run_manifest.json` | CSV / JSON | §7 | Yes (final run only) |
| `storage/feedback.db` | SQLite | §8 (OPTIONAL) | No |

## 2. Catalogue (`catalog.parquet`)
| Column | Arrow type | Nullable | Rule |
|---|---|---|---|
| `movie_id` | int32 | no | MovieLens movieId; primary key; file sorted by it |
| `title` | string | no | Title without the year suffix |
| `year` | int16 | yes | From "(YYYY)" |
| `genres` | list<string> | no | Registry genre names; may be empty |
| `tags` | list<string> | no | Normalised, top 20; may be empty |
| `rating` | float32 | yes | Mean rating |
| `votes` | int32 | no | Count of ratings (0 if none) |
| `bayes` | float32 | no | Bayesian rating (m = 10) |
| `embed_text` | string | no | Text that was embedded |
| `runtime` | int16 | yes | OPTIONAL, from enrichment only |
| `language` | string | yes | OPTIONAL, from enrichment only |

## 3. Artifacts and Manifest
| File | Content |
|---|---|
| `embeddings.npy` | float32 [N, 384], L2-normalised, row i ↔ `ids.npy[i]` |
| `ids.npy` | int64 [N], equals `catalog.movie_id` order |
| `faiss.index` | `IndexIDMap(IndexFlatIP(384))` with the same ids |

```json
{
  "manifest_version": "1.0",
  "dataset": {"name": "ml-latest-small", "downloaded": "2026-10-15",
              "files": {"movies.csv": {"sha256": "…", "rows": 9742},
                        "ratings.csv": {"sha256": "…", "rows": 100836},
                        "tags.csv": {"sha256": "…", "rows": 3683},
                        "links.csv": {"sha256": "…", "rows": 9742}},
              "orphans_dropped": {"ratings": 0, "tags": 0}},
  "catalog": {"rows": 9742, "built": "2026-10-15T10:02:11Z", "prepare_version": "1.0",
              "coverage": {"year": 0.998, "rating": 0.998, "tags": 0.16, "genres": 0.996}},
  "model": {"name": "sentence-transformers/all-MiniLM-L6-v2", "dim": 384, "normalized": true},
  "index": {"backend": "faiss_flat", "n": 9742, "built": "…", "embed_text_version": "1.0"}
}
```
Row counts and coverage above are placeholders showing the shape; the real values are written by the pipeline.

## 4. Configuration Files
`config/registry.yaml`:
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
`config/runtime.yaml`:
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

## 5. Benchmark and Judgments
`benchmark/requests.jsonl`, one object per line:

```json
{"id": "R001", "split": "dev", "category": "soft_exclusion",
 "text": "thoughtful sci-fi mystery after 2010, little romance, top 5",
 "gold_ir": { ...canonical CompiledQuery JSON after passes, without source/diagnostics... },
 "gold_diagnostics": [],
 "baseline_spec": { ...BaselineSpec... }}
```

Categories (10 valid × 10 requests): `single_genre, multi_genre, descriptor_only, hard_exclusion, soft_exclusion, year, rating_votes, hedged, limit, combined`; plus 20 `invalid` (contradiction, empty range, unavailable field, unknown field, nonsense). Split: 40 dev / 80 test, stratified by category.

`benchmark/judgments.csv`: `request_id, movie_id, judge, grade(0|1|2)` for 40 valid test requests (pooled Top-10 of all systems, blind).

`BaselineSpec` JSON fields: `semantic_text: str, pos_genres: [str], pos_terms: [str], neg_soft: [Preference], hard: [Constraint], soft_constraints: [Constraint], limit: int`. Invalid items have `gold_ir: null` and `baseline_spec: null`.

`judgments.csv` columns: `request_id` (str), `movie_id` (int), `judge` (A/B), `grade` (0/1/2), `final_grade` (0/1/2 after adjudication).

## 6. Trace (`traces/<request_id>.json`)
Defined in Logging, Tracing and Observability §3, validated by `runtime/trace_schema.json`.

## 7. Results
| File | Columns |
|---|---|
| `compiler_metrics.csv` | metric, split, value, n, target, passed |
| `equivalence.csv` | request_id, rules, same_ids, same_scores, same_hard_outcomes, same_diagnostics, ms_unoptimized, ms_optimized |
| `recommendation_metrics.csv` | system, metric, k, value, n_requests |
| `latency.csv` | request_id, optimize, stage_or_opcode, run, ms |
| `run_manifest.json` | git_commit, created, config_sha256, registry_sha256, dataset sha256s, model, python, packages (pip freeze) |

## 8. Optional SQLite Feedback (P1)
```sql
CREATE TABLE IF NOT EXISTS feedback (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  created_utc   TEXT    NOT NULL,              -- ISO-8601
  request_text  TEXT    NOT NULL,
  ir_hash       TEXT    NOT NULL,
  movie_id      INTEGER NOT NULL,
  rank          INTEGER NOT NULL,
  verdict       TEXT    NOT NULL CHECK (verdict IN ('up','down')),
  app_version   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_feedback_ir ON feedback(ir_hash);
```
No user identifiers are stored.

## 9. Schema Versioning
Every JSON document carries a `*_version` field (`ir_version`, `trace_version`, `manifest_version`, `registry_version`, `runtime_version`). Same major version: readers accept and default missing fields. New major version: readers reject with a clear message. Changes are recorded in `docs/CHANGELOG.md`.
