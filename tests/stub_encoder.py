"""Deterministic stand-in for the sentence encoder (Testing Plan §6 toy_embeddings).

Each text maps to a seeded 8-d unit vector, so search order is fixed and no model is needed.
"""

from __future__ import annotations

import hashlib

import numpy as np

DIM = 8


class StubEncoder:
    def __init__(self) -> None:
        self.calls = 0

    def encode(self, texts: list[str]) -> np.ndarray:
        self.calls += 1
        out = np.empty((len(texts), DIM), dtype=np.float32)
        for i, t in enumerate(texts):
            seed = int.from_bytes(hashlib.sha256(t.encode("utf-8")).digest()[:8], "little")
            v = np.random.default_rng(seed).standard_normal(DIM).astype(np.float32)
            out[i] = v / np.linalg.norm(v)
        return out
