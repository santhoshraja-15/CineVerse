"""Encode the catalogue and build the exact search index (steps I1–I6).

Spec: CineVerse_Dataset_and_Data_Pipeline_Specification §5; Database and Data Schemas §3.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from cineverse.config import get_paths, load_runtime_config
from cineverse.runtime.catalog import Catalog
from cineverse.runtime.semantic_index import FaissFlatIndex, NumpyIndex, TextEncoder

log = logging.getLogger(__name__)

EMBED_TEXT_VERSION = "1.0"
SELF_CHECK_N = 50


def build_faiss(embeddings: np.ndarray, ids: np.ndarray) -> Any:
    import faiss

    index = faiss.IndexIDMap(faiss.IndexFlatIP(embeddings.shape[1]))
    index.add_with_ids(embeddings, ids)
    return index


def self_check(index: NumpyIndex | FaissFlatIndex, texts: list[str], seed: int) -> tuple[int, int]:
    """I5: a movie's own text retrieves itself at rank 1 (or tied with rank 1 at 1e-6)."""
    rng = random.Random(seed)
    sample = rng.sample(range(len(index.ids)), min(SELF_CHECK_N, len(index.ids)))
    ok = 0
    for i in sample:
        rl = index.search(texts[i], None, 5)
        mid = int(index.ids[i])
        top = round(rl.scores[0], 6) if rl.scores else None
        tied = {m for m, s in zip(rl.ids, rl.scores, strict=True) if round(s, 6) == top}
        ok += mid in tied and top is not None and top > 0.99
    return ok, len(sample)


def build(
    catalog_path: Path,
    artifacts_dir: Path,
    backend: str,
    encoder: TextEncoder,
    model_name: str,
    seed: int,
) -> dict[str, Any]:
    """I1–I6. Returns the manifest sections written."""
    catalog = Catalog.load(catalog_path)  # I1
    texts = [str(t) for t in catalog.column("embed_text")]
    ids = catalog.all_ids().astype(np.int64)

    t0 = time.perf_counter()
    embeddings = np.asarray(encoder.encode(texts), dtype=np.float32)  # I2
    encode_s = time.perf_counter() - t0

    artifacts_dir.mkdir(parents=True, exist_ok=True)  # I3
    np.save(artifacts_dir / "embeddings.npy", embeddings)
    np.save(artifacts_dir / "ids.npy", ids)

    index: NumpyIndex | FaissFlatIndex
    if backend == "faiss_flat":  # I4
        import faiss

        faiss_index = build_faiss(embeddings, ids)
        faiss.write_index(faiss_index, str(artifacts_dir / "faiss.index"))
        index = FaissFlatIndex(faiss_index, embeddings, ids, encoder)
    else:
        index = NumpyIndex(embeddings, ids, encoder)

    passed, total = self_check(index, texts, seed)  # I5
    log.info("self-check %d/%d", passed, total)
    print(f"self-check {passed}/{total}")

    sections = {  # I6
        "model": {"name": model_name, "dim": int(embeddings.shape[1]), "normalized": True},
        "index": {
            "backend": backend,
            "n": len(ids),
            "built": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "embed_text_version": EMBED_TEXT_VERSION,
        },
    }
    manifest_path = artifacts_dir / "manifest.json"
    manifest: dict[str, Any] = {}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.setdefault("manifest_version", "1.0")
    manifest.update(sections)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    log.info("encoded %d texts in %.1f s", len(texts), encode_s)
    if passed != total:
        log.warning("I5 self-check failed for %d movies", total - passed)
    return sections


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build CineVerse embeddings and index.")
    args = parser.parse_args(argv)
    del args
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    from cineverse.runtime.embeddings import Encoder

    paths, cfg = get_paths(), load_runtime_config()
    encoder = Encoder(cfg.model_name)
    build(paths.catalog_path, paths.artifacts_dir, cfg.index_backend, encoder, cfg.model_name,
          cfg.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
