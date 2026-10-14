# CineVerse — Environment Setup and Dependencies
**Environment Setup and Dependencies · v1.0**

Team 14 (Santhoshraja S, Siddharth P, Keshore G) · 2026-10-14 · Status: Draft for team review

---

## Contents
1. Requirements · 2. Dependencies · 3. Setup (Windows) · 4. Setup (macOS / Linux) · 5. Data and Model · 6. Verification · 7. Troubleshooting · 8. Updating Dependencies

## 1. Requirements
| Item | Requirement |
|---|---|
| OS | Windows 10/11 x64, macOS 13+ (Apple Silicon or Intel), Ubuntu 22.04+ |
| Python | 3.11.x (64-bit). Other versions are not supported for the course build |
| RAM | 8 GB minimum |
| Disk | ~2 GB (PyTorch CPU wheel, model cache, data, artifacts) |
| Network | Only for the first install, dataset download and model download |
| Tools | Git; optional VS Code with Python and Ruff extensions |

## 2. Dependencies

`requirements.txt` (runtime):
```
pandas>=2.2,<3
numpy>=1.26,<3
pyarrow>=15
sentence-transformers>=3.0
faiss-cpu>=1.8
pydantic>=2.7,<3
pyyaml>=6
streamlit>=1.36
```
`requirements-dev.txt`:
```
pytest>=8
pytest-cov>=5
ruff>=0.6
mypy>=1.10
jsonschema>=4.22
```
OPTIONAL extras: `fastapi`, `uvicorn` (T33); `requests`, `python-dotenv` (T32).

| Package | Used for | Layer |
|---|---|---|
| pandas, pyarrow | Catalogue build and load | Data, Runtime |
| numpy | Arrays, NumPy search backend | Runtime |
| sentence-transformers (pulls torch, transformers) | Query and movie embeddings | Runtime, Data |
| faiss-cpu | Exact inner-product search | Runtime |
| pydantic | IR models and validation | Contract |
| pyyaml | Registry and runtime config | Data |
| streamlit | UI | Presentation |
| pytest, jsonschema | Tests, trace schema validation | Dev |

This set was checked to resolve for Python 3.11 on Windows x64 (dry-run resolution). Versions are frozen into `requirements.lock` by each team after Step 2 passes on all three laptops.

## 3. Setup (Windows, PowerShell)
```powershell
git clone <repo-url> cineverse; cd cineverse
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt
python -c "import faiss, sentence_transformers, pydantic, streamlit; print('ok')"
```
If `Activate.ps1` is blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## 4. Setup (macOS / Linux)
```bash
git clone <repo-url> cineverse && cd cineverse
python3.11 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt
python -c "import faiss, sentence_transformers, pydantic, streamlit; print('ok')"
```

## 5. Data and Model
1. Download `ml-latest-small.zip` from https://grouplens.org/datasets/movielens/ and extract to `data/raw/ml-latest-small/`.
2. `python -m cineverse.data.prepare`
3. `python -m cineverse.data.build_index` (downloads `sentence-transformers/all-MiniLM-L6-v2` once to the Hugging Face cache, about 90 MB).
4. For offline use afterwards set `HF_HUB_OFFLINE=1` (see Configuration and Secrets Management).

## 6. Verification
```bash
pytest -q -m "not full"     # fast suite
pytest -q                   # full suite (needs data + index)
streamlit run app/streamlit_app.py
```
Expected: all tests pass; the app opens on http://localhost:8501 and EX01 returns 5 results.

## 7. Troubleshooting
| Symptom | Cause | Fix |
|---|---|---|
| `ImportError: faiss` | No wheel for the platform | Set `index_backend: numpy` in `config/runtime.yaml`; results are identical |
| Torch install very large/slow | Default wheel | `pip install torch --index-url https://download.pytorch.org/whl/cpu` before requirements |
| `OSError` loading model | Offline before first download | Connect once, run `build_index`, then use `HF_HUB_OFFLINE=1` |
| `UnicodeDecodeError` reading CSV | Wrong encoding | `prepare.py` reads with `encoding="utf-8"` explicitly |
| Streamlit port in use | Another app | `streamlit run app/streamlit_app.py --server.port 8502` |
| Different results between laptops | Different snapshot or config | Compare `artifacts/manifest.json` checksums and `runtime.yaml` |

## 8. Updating Dependencies
Change `requirements.txt` only via a task; re-run the full suite on all laptops; regenerate `requirements.lock`; note in CHANGELOG.
