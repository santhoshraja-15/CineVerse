"""Sentence-Transformers encoder: L2-normalised float32 vectors.

Confirmed against the installed sentence-transformers 6.1: SentenceTransformer(model, device=...)
and encode(inputs, batch_size=..., normalize_embeddings=True, convert_to_numpy=True).
Spec: CineVerse_Recommendation_Engine_Specification §2 (11.2); Dataset Spec §5 I1–I2.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import numpy as np

log = logging.getLogger(__name__)

BATCH_SIZE = 64


class ModelUnavailable(RuntimeError):
    """The embedding model cannot be loaded (not cached and offline, or broken install)."""


class Encoder:
    def __init__(self, model_name: str) -> None:
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(model_name, device="cpu")
        except Exception as exc:  # any load failure means the semantic channel is unavailable
            raise ModelUnavailable(f"cannot load {model_name}: {exc}") from exc
        self.model_name = model_name
        dim = self._model.get_sentence_embedding_dimension()
        self.dim = int(dim) if dim is not None else 0

    def encode(self, texts: Sequence[str], *, show_progress: bool = False) -> np.ndarray:
        vectors = self._model.encode(
            list(texts),
            batch_size=BATCH_SIZE,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=show_progress,
        )
        return np.asarray(vectors, dtype=np.float32)
