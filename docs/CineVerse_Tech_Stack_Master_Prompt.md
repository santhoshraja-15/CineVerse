# CineVerse — Tech Stack Master Prompt
**Tech Stack Master Prompt · v1.0**

Team 14 (Santhoshraja S, Siddharth P, Keshore G) · 2026-10-14 · Status: Draft for team review

---

> **Use.** Paste the prompt in §2 into Claude Code at the start of Roadmap step 2 (task T03). It sets up and verifies the technology stack on the current machine without adding anything outside the approved list. §1 is the approved stack; §3 is what a correct run produces.

## 1. Approved Stack

| Layer | Technology | Version policy | Why | Not allowed instead |
|---|---|---|---|---|
| Language | Python | 3.11.x | Library support on all OSes | 3.12+ for the course build, Conda-only setups |
| Compiler structures | dataclasses (stdlib), Pydantic v2 | `pydantic>=2.7,<3` | Frozen AST/tokens; validated IR | attrs, marshmallow |
| Parser | Hand-written recursive descent | — | Explicit FIRST sets, spans, recovery | PLY, ANTLR, Lark, spaCy parsers |
| Data | pandas, NumPy, PyArrow | `pandas>=2.2,<3`, `numpy>=1.26,<3`, `pyarrow>=15` | Catalogue and arrays | Polars, Spark |
| Embeddings | sentence-transformers, model `all-MiniLM-L6-v2` | `>=3.0` | Small, CPU-friendly, 384-d | OpenAI/LLM embeddings, multiple models |
| Vector search | faiss-cpu `IndexIDMap(IndexFlatIP)`; NumPy fallback | `>=1.8` | Exact search | HNSW/IVF in CORE, vector databases |
| Config | PyYAML | `>=6` | Registry and runtime YAML | — |
| UI | Streamlit | `>=1.36` | Fast UI with tabs | React, Flask templates |
| Tests | pytest (+ pytest-cov, jsonschema) | `>=8` | Unit, golden, gates | unittest-only |
| Lint/format/type | ruff, mypy | `ruff>=0.6`, `mypy>=1.10` | Consistency | black+flake8+isort trio |
| OPTIONAL | FastAPI + uvicorn (T33); requests + python-dotenv (T32); SQLite stdlib (T34) | latest compatible | Only after all P0 | Django, PostgreSQL, Docker |

## 2. The Prompt

```text
You are setting up the technology stack for CineVerse, a Compiler Design course project
(natural-language movie requests compiled into optimized plans executed by a hybrid
recommender). Work only on environment and scaffolding. Do not implement any compiler
stage or runtime operator in this session.

APPROVED STACK (do not add, remove or substitute anything):
- Python 3.11.x
- Runtime deps: pandas>=2.2,<3; numpy>=1.26,<3; pyarrow>=15; sentence-transformers>=3.0;
  faiss-cpu>=1.8; pydantic>=2.7,<3; pyyaml>=6; streamlit>=1.36
- Dev deps: pytest>=8; pytest-cov>=5; ruff>=0.6; mypy>=1.10; jsonschema>=4.22
- Embedding model: sentence-transformers/all-MiniLM-L6-v2
- Vector index: faiss IndexIDMap(IndexFlatIP(384)); NumPy exact backend as fallback

TASKS
1. Check the interpreter: run `python --version`. If it is not 3.11.x, stop and tell me
   how to install 3.11 for this OS. Do not continue with another version.
2. Create `.venv` with Python 3.11 and activate it (show the exact command for this OS).
3. Write requirements.txt and requirements-dev.txt with exactly the ranges above.
4. Install them. If faiss-cpu fails to install, do NOT try other vector libraries:
   record the error, set `index_backend: numpy` in config/runtime.yaml, and continue.
5. Verify imports with one command and print versions:
   python -c "import sys,pandas,numpy,pyarrow,pydantic,yaml,streamlit,sentence_transformers;
   print(sys.version); [print(m.__name__, m.__version__) for m in (pandas,numpy,pyarrow,pydantic,streamlit,sentence_transformers)]"
   and separately: python -c "import faiss; print('faiss', faiss.__version__)"
6. Before writing any code that calls sentence-transformers, faiss or streamlit, open the
   installed package's documentation or source (pip show -f, help(), or the official docs)
   and confirm the exact function names and signatures you will use:
   SentenceTransformer.encode(..., normalize_embeddings=True), faiss.IndexIDMap,
   faiss.IndexFlatIP, index.add_with_ids, faiss.SearchParameters, faiss.IDSelectorBatch,
   st.cache_resource, st.tabs, st.toggle. Report anything that differs from these names.
7. Create the repository skeleton exactly as in
   docs/CineVerse_Repository_Structure_and_Coding_Standards.md §1 (empty modules with a
   one-line docstring "Spec: <document> §<n>"), plus pyproject.toml with ruff (line 100),
   pytest (markers: full) and mypy settings.
8. Add tests/test_smoke.py (imports every package) and tests/test_layers.py (rules from
   docs/CineVerse_Layer_Architecture_Requirements.md §4).
9. Run `ruff check .` and `pytest -q`. Both must pass.
10. Write requirements.lock with `pip freeze`.
11. Report: Python version, every package version, faiss status, test output, and any
    deviation from this prompt.

DO NOT: add packages not listed; upgrade Python; install CUDA/GPU builds; create Docker
files; write business logic; change config values other than index_backend.

VERIFY: `pytest -q` shows the smoke and layer tests passing; the import command prints
all versions; requirements.lock exists.
```

## 3. Expected Result
- `.venv/` with Python 3.11; `requirements*.txt` and `requirements.lock` committed.
- Skeleton matches the repository tree; `pytest -q` green (smoke + layers).
- A short report listing versions and, if needed, the NumPy-backend decision (record it in the Project Control decision log).
