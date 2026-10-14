# CineVerse — Dataset and Data Pipeline Specification
**Dataset and Data Pipeline Specification · v1.0**

Team 14 (Santhoshraja S, Siddharth P, Keshore G) · 2026-10-14 · Status: Draft for team review

---

> **Normative.** Defines the source dataset, the canonical catalogue, the preparation and index-build pipelines, validation checks, manifests and licensing obligations. Code: `cineverse/data/prepare.py`, `cineverse/data/build_index.py`, `cineverse/runtime/catalog.py`.

## Contents
1. Source Dataset · 2. Canonical Catalogue · 3. Preparation Pipeline · 4. Validation Checks · 5. Index Build · 6. Manifest · 7. Optional Enrichment · 8. Licensing and Provenance · 9. Test Obligations

## 1. Source Dataset
| Property | Value |
|---|---|
| Dataset | MovieLens latest-small (GroupLens Research) |
| Location | https://grouplens.org/datasets/movielens/ → `ml-latest-small.zip` |
| Files used | `movies.csv` (movieId, title, genres), `ratings.csv` (userId, movieId, rating, timestamp), `tags.csv` (userId, movieId, tag, timestamp), `links.csv` (movieId, imdbId, tmdbId) |
| Approximate size | ~9,700 movies; ~100,000 ratings by 610 users; ~3,700 tag applications |
| Rating scale | 0.5–5.0 in steps of 0.5 |
| Volatility | "latest" datasets change over time; the snapshot is pinned by SHA-256 in the manifest |
| Not present | plot summaries, runtime, language, cast |

Place files in `data/raw/ml-latest-small/`. Never edit raw files; never commit them.

## 2. Canonical Catalogue
`python -m cineverse.data.prepare` reads `data/raw/ml-latest-small/{movies,ratings,tags,links}.csv` and writes `data/processed/catalog.parquet`:

| Column | Type | Rule |
|---|---|---|
| `movie_id` | int | `movieId`, unique |
| `title` | str | title without the "(YYYY)" suffix |
| `year` | int \| null | parsed from "(YYYY)" suffix |
| `genres` | list[str] | split on "\|"; "(no genres listed)" → [] |
| `tags` | list[str] | lower-cased, trimmed, de-duplicated, top 20 by frequency |
| `rating` | float \| null | mean rating |
| `votes` | int | rating count (0 if none) |
| `bayes` | float | `(votes·rating + m·C)/(votes + m)`, m = 10, C = global mean |
| `embed_text` | str | `"{title}. Genres: {g1, g2}. Tags: {t1, t2}."` (genre display names) |

`artifacts/manifest.json`: dataset name, download date, SHA-256 of each raw file, row counts, coverage per field, model name, embedding dimension, index type, `embed_text` template version, creation time.

## 3. Preparation Pipeline (`python -m cineverse.data.prepare`)
| Step | Operation | Output / check |
|---|---|---|
| P1 | Hash raw files (SHA-256), record sizes and download date | manifest.dataset |
| P2 | Load CSVs with explicit dtypes (`movieId: int32`, `rating: float32`, ...) | DataFrames |
| P3 | Validate (§4); abort on any failure with the check id | — |
| P4 | Title: strip trailing `(YYYY)` (regex `\s*\((\d{4})\)\s*$`) into `year`; handle titles with alternative names in parentheses before the year | `title`, `year` |
| P5 | Genres: split on the pipe character; `(no genres listed)` → `[]`; validate against registry genres | `genres` |
| P6 | Ratings: group by movieId → mean (`rating`), count (`votes`); global mean C; `bayes = (votes·rating + m·C)/(votes + m)`, m = 10; movies with no ratings: `rating = null`, `votes = 0`, `bayes = C` | rating columns |
| P7 | Tags: strip, lower-case, collapse whitespace, drop empty; count per (movie, tag); keep top 20 by count then alphabetically | `tags` |
| P8 | `embed_text = f"{title}. Genres: {', '.join(display(g) for g in genres)}. Tags: {', '.join(tags)}."` (omit the Tags part when empty) | `embed_text` |
| P9 | Write `data/processed/catalog.parquet` (sorted by movie_id); write coverage stats | parquet + manifest.coverage |

## 4. Validation Checks
| ID | Check | On failure |
|---|---|---|
| D1 | Required columns present with expected names | abort |
| D2 | `movieId` unique in movies.csv | abort |
| D3 | Every ratings/tags/links movieId exists in movies.csv | drop orphan rows, count them in manifest |
| D4 | Ratings within [0.5, 5.0] | abort |
| D5 | Every genre string in registry or `(no genres listed)` | abort (registry must be updated) |
| D6 | ≥ 95% of titles yield a year | warn; record coverage |
| D7 | Row counts within ±20% of the manifest from the previous build (if any) | warn |

## 5. Index Build (`python -m cineverse.data.build_index`)
| Step | Operation |
|---|---|
| I1 | Load `catalog.parquet`; encoder `sentence-transformers/all-MiniLM-L6-v2` |
| I2 | Encode `embed_text` in catalogue order, batch 64, `normalize_embeddings=True`, float32 |
| I3 | Save `artifacts/embeddings.npy` (N × 384) and `artifacts/ids.npy` (N int64) |
| I4 | If `index_backend = faiss_flat`: `faiss.IndexIDMap(faiss.IndexFlatIP(384))`, `add_with_ids(emb, ids)`, `faiss.write_index(..., "artifacts/faiss.index")` |
| I5 | Self-check: for 50 random movies, searching its own vector returns itself at rank 1 (score ≈ 1.0) |
| I6 | Update manifest: model name, dimension, normalisation, backend, N, build time, `embed_text` template version |

Expected build time on a laptop CPU: a few minutes for ~9,700 short texts (measure and record; do not assume).

## 6. Manifest (`artifacts/manifest.json`)
Schema in Database and Data Schemas §3. The registry, the evaluation run manifest and the UI footer read it.

## 7. Optional Enrichment (P1, `data/enrich_tmdb.py`)
- Uses `links.csv` `tmdbId` → TMDB API movie details (runtime, original_language, overview).
- Requires `TMDB_API_KEY` in `.env` (Configuration and Secrets Management); respects TMDB terms and attribution.
- Writes `data/processed/enrichment.parquet`; registry marks `runtime`/`language` available only if coverage ≥ 90%.
- Never required for the CORE build or tests.

## 8. Licensing and Provenance
- Follow the GroupLens MovieLens usage terms (README in the zip): research use, no redistribution of the data, cite Harper & Konstan (2015).
- Do not commit `data/raw`, `data/processed` or `artifacts`; provide scripts to rebuild them.
- The report cites the dataset and the snapshot checksum.

## 9. Test Obligations
| Test | Content |
|---|---|
| `test_prepare.py` | Toy CSVs: year parsing (with/without year, alternative titles), genre split, no-genre case, Bayesian formula, tag normalisation and top-20, orphan dropping, each D-check fails correctly |
| `test_catalog.py` | Load parquet; lookups; `all_ids()` sorted |
| `test_build_index.py` | Toy catalogue of 20 movies; self-retrieval check; ids alignment; NumPy and FAISS backends identical |
