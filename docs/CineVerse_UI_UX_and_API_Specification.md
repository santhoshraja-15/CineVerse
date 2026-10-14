# CineVerse — UI/UX and API Specification
**UI/UX and API Specification · v1.0**

Team 14 (Santhoshraja S, Siddharth P, Keshore G) · 2026-10-14 · Status: Draft for team review

---

> **Purpose.** Defines the Streamlit interface (CORE), the Python API (CORE) and the optional HTTP API (P1). The UI has two jobs: make recommendations pleasant to get, and make every compiler stage visible for the examiner.

## Contents
1. UX Principles · 2. Streamlit Interface · 3. Python API · 4. Optional HTTP API · 5. Accessibility and Error Display · 6. Acceptance Checklist

## 1. UX Principles
1. One box, one button; results in seconds.
2. Never hide a warning: if a condition was not applied, say so above the results.
3. Every result says why.
4. The compiler is one click away, never in the way.
5. Same input → same output (no randomness in the UI).

## 2. Streamlit Interface (`app/streamlit_app.py`)

### 2.1 Layout
```
┌──────────────────────────────────────────────────────────────────────────┐
│ CineVerse — describe a movie                                             │
│ [ thoughtful sci-fi mystery after 2010, little romance, top 5       ] [Go]│
│ Try: (no romance) (only comedies in the 90s) (comedy under 2 hours) …     │
│ ☐ Optimizer on (default ✓)     catalogue: ml-latest-small · 9,742 movies  │
├──────────────────────────────────────────────────────────────────────────┤
│ ⚠ S105 runtime is not available in this catalogue; "under 2 hours" …     │
├──────────────────────────────────────────────────────────────────────────┤
│ 1. Title (2014) · Sci-Fi, Mystery · score 0.86                           │
│    • Genres Sci-Fi and Mystery match your request                        │
│    • Tagged 'thought-provoking', matching 'thoughtful'                   │
│    • Released 2014 (from 2011)                                           │
│ 2. …                                                                     │
├──────────────────────────────────────────────────────────────────────────┤
│ ▸ Compiler view                                                          │
│   [Tokens] [AST] [Semantic] [IR] [Plan] [Program] [Timings] [Trace]      │
└──────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Components
| Component | Widget | Content |
|---|---|---|
| Request input | `st.text_input` + button; Enter submits | Max 300 chars; placeholder shows an example |
| Example chips | `st.button` row | 6 curated requests covering hard/soft/numeric/error cases |
| Optimizer toggle | `st.toggle` | Default on; flips `compile(optimize=…)` |
| Diagnostics banner | `st.error` / `st.warning` / `st.info` by severity | Code, message, hint; request text with the span highlighted (`<mark>`) |
| Result cards | `st.container` per result | Rank, title, year, genres, score (2 decimals), up to 4 reasons |
| Empty state | `st.info` | X202 message: "No movie satisfies all strict conditions: …" listing them |
| Compiler view | `st.expander` + `st.tabs` | See 2.3 |
| Footer | `st.caption` | Dataset checksum prefix, model, IR version, build commit |

### 2.3 Compiler view tabs
| Tab | Shows | Source field |
|---|---|---|
| Tokens | Table: type, lexeme, value, span; FILLER greyed | `CompilationResult.tokens` |
| AST | Indented tree (`st.code`) + JSON toggle | `ast` |
| Semantic | Table per node: field, op, value, strictness, polarity, applied | `semantic.annotations` |
| IR | Two columns: lowered vs after passes; hash; rule log for O1/O2 | `ir_lowered`, `ir`, `rule_log` |
| Plan | Graphviz of unoptimized and optimized plans; applied O3/O4 highlighted | `plan_unoptimized`, `plan` |
| Program | Printed SSA program (`st.code`) before/after | codegen output |
| Timings | Bar chart per stage and per instruction; optimized vs unoptimized when toggled | `timings_ms`, trace execution |
| Trace | Full JSON with download button | trace |

### 2.4 Performance
`@st.cache_resource` for `get_context()` (catalogue, registry, encoder, index). Compilation and execution run per request; target p95 < 1.5 s end-to-end warm.

## 3. Python API (CORE)
```python
from cineverse import recommend
comp, exe = recommend("no romance, after 2015", optimize=True)
comp.ok                 # bool
comp.diagnostics        # list[Diagnostic]
comp.ir.to_json()       # canonical IR
print("\n".join(map(str, comp.program)))   # printed SSA program
exe.results             # list[Recommendation]
exe.trace               # dict (trace_version 1.0)
```
`recommend` returns `(comp, None)` when `comp.ok` is false.

## 4. Optional HTTP API (P1, FastAPI, `api/main.py`)
| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/health` | — | `{"status":"ok","semantic":true,"catalog_rows":9742}` |
| POST | `/compile` | `{"text": str, "optimize": bool}` | `{"ok", "diagnostics", "ir", "program", "rule_log"}` |
| POST | `/recommend` | `{"text": str, "optimize": bool}` | `{"ok", "diagnostics", "results": [Recommendation], "request_id"}` |
| GET | `/trace/{request_id}` | — | trace JSON |

Errors: invalid body → 422 (FastAPI default); compile ERROR → 200 with `ok: false` and diagnostics (a bad request sentence is not an HTTP error). Bind to `127.0.0.1` only.

## 5. Accessibility and Error Display
- Severity uses icon + word + colour (not colour alone).
- Span highlighting also shows the quoted words in the message.
- All text selectable; JSON downloadable.
- Keyboard: Enter submits; tabs reachable by Tab key (Streamlit default).

## 6. Acceptance Checklist
- [ ] EX01 shows 5 results with reasons and an O4 highlight in Plan.
- [ ] EX07 shows S112 (info) and S105 (warning) above comedy results.
- [ ] EX08 shows S107 with both "only horror" and "no horror" highlighted; no results section.
- [ ] Toggling the optimizer keeps results identical and changes the Timings tab.
- [ ] Trace download validates against the schema.
