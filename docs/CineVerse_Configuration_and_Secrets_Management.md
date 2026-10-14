# CineVerse — Configuration and Secrets Management
**Configuration and Secrets Management · v1.0**

Team 14 (Santhoshraja S, Siddharth P, Keshore G) · 2026-10-14 · Status: Draft for team review

---

> **Summary.** The CORE build has **no secrets**. All behaviour is configured by two committed YAML files. The only secret is the OPTIONAL TMDB API key, kept in an uncommitted `.env`.

## Contents
1. Configuration Sources · 2. registry.yaml · 3. runtime.yaml · 4. Loading and Validation · 5. Environment Variables · 6. Secrets · 7. Configuration Change Control

## 1. Configuration Sources (precedence high → low)
| Source | Scope | Committed |
|---|---|---|
| Function arguments (`compile(optimize=…, rules=…)`) | One call | — |
| Environment variables (`CINEVERSE_*`) | Process | No |
| `config/runtime.yaml` | Runtime parameters | Yes |
| `config/registry.yaml` + catalogue statistics | Request language and symbol table | Yes |

## 2. `config/registry.yaml`
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

## 3. `config/runtime.yaml`
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
| Key | Meaning | Changed by |
|---|---|---|
| `model_name` | Embedding model | Decision log only |
| `index_backend` | `faiss_flat` or `numpy` (both exact) | Per machine if FAISS fails |
| `candidate_budget` | C per source | Tuning (dev only) |
| `rrf_k` | RRF constant | Fixed at 60 |
| `soft.beta/lambda/mu` | Soft weights | Tuning (dev only), then frozen |
| `metadata.tag_match_weight`, `bayes_m` | Metadata scoring | Fixed |
| `mmr.lambda` | OPTIONAL | Tuning when MMR exists |
| `seed` | All randomness (tests, bootstrap) | Fixed |

## 4. Loading and Validation
`cineverse/config.py` loads YAML into frozen dataclasses and validates: required keys present; numeric ranges (`candidate_budget` 10–2000, weights 0–1, `rrf_k` > 0); backend in the allowed set; registry genres unique; every alias maps to known genres; every unit maps to a declared field. A failure raises `ConfigError` at start-up with the key path. The SHA-256 of each file is written into traces and `run_manifest.json`.

## 5. Environment Variables
| Variable | Default | Purpose |
|---|---|---|
| `CINEVERSE_CONFIG_DIR` | `config` | Alternative config folder (tests) |
| `CINEVERSE_DATA_DIR` | `data` | Data root |
| `CINEVERSE_ARTIFACTS_DIR` | `artifacts` | Artifacts root |
| `CINEVERSE_INDEX_BACKEND` | (from YAML) | Override backend |
| `CINEVERSE_LOG_LEVEL` | `INFO` | Logging level |
| `CINEVERSE_PERSIST_TRACES` | `0` | Write traces to `traces/` |
| `HF_HUB_OFFLINE` | unset | Set `1` after the model is cached |
| `TMDB_API_KEY` | unset | OPTIONAL enrichment only |

`.env.example`:
```
# Copy to .env (never commit .env)
CINEVERSE_LOG_LEVEL=INFO
CINEVERSE_PERSIST_TRACES=0
# HF_HUB_OFFLINE=1
# TMDB_API_KEY=            # only for OPTIONAL task T32
```

## 6. Secrets
- Only `TMDB_API_KEY` (OPTIONAL). Stored in `.env` (git-ignored) or the OS environment; read via `os.environ` in `data/enrich_tmdb.py` only.
- Never logged, never written to traces, manifests or results; logging filter masks values of keys ending in `_KEY`.
- Rotating: regenerate on the TMDB site, update `.env`; nothing else changes.
- Pre-commit check: `git grep -nE "(api_key|API_KEY)\s*=\s*['\"][A-Za-z0-9]"` must return nothing.

## 7. Configuration Change Control
Changes to `registry.yaml` (language) or frozen runtime weights require: a Project Control decision log entry, CHANGELOG entry, version bump (`registry_version`/`runtime_version`), and a full test + golden regeneration review.
