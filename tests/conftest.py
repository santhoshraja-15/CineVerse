"""Shared fixtures. Spec: Testing and Quality Assurance Plan §6.

The toy catalogue uses synthetic titles only (Master Instructions §A, anti-hallucination rule 5).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cineverse.config import MetadataConfig, RuntimeConfig, SoftConfig
from cineverse.runtime.catalog import Catalog

# id, title, year, genres, tags, rating, votes, bayes
TOY_MOVIES = [
    (1, "Toy Orbit", 2012, ("Sci-Fi", "Mystery"), ("thought-provoking", "space"), 4.2, 120, 4.05),
    (2, "Toy Heist Night", 2005, ("Crime", "Thriller"), ("heist", "twist ending"), 3.9, 80, 3.80),
    (3, "Toy Love Letters", 2015, ("Romance", "Comedy"), ("feel-good",), 3.5, 40, 3.45),
    (4, "Toy Dark Woods", 1999, ("Horror",), ("gore", "dark"), 3.1, 30, 3.20),
    (5, "Toy Time Loop", 2014, ("Sci-Fi", "Romance"), ("time travel", "thoughtful"), 4.0, 60,
     3.90),
    (6, "Toy Old West", 1965, ("Western",), (), 3.8, 15, 3.60),
    (7, "Toy Unknown Year", None, ("Drama",), ("slow",), None, 0, 3.50),
    (8, "Toy Laugh Track", 1994, ("Comedy",), ("funny", "feel-good"), 3.7, 200, 3.68),
    (9, "Toy Mystery Manor", 2011, ("Mystery", "Thriller"), ("twist ending", "dark"), 3.9, 90,
     3.82),
    (10, "Toy Galaxy War", 2017, ("Sci-Fi", "Action", "War"), ("space", "violent"), 3.3, 50, 3.30),
    (11, "Toy Cartoon Pals", 2008, ("Animation", "Children", "Comedy"), ("pixar",), 4.1, 70, 3.95),
    (12, "Toy Quiet Drama", 2016, ("Drama",), (), 3.6, 5, 3.52),
]


def toy_columns() -> dict[str, np.ndarray]:
    def obj(values: list) -> np.ndarray:
        arr = np.empty(len(values), dtype=object)
        arr[:] = values
        return arr

    rows = TOY_MOVIES
    return {
        "movie_id": np.array([r[0] for r in rows], dtype=np.int64),
        "title": obj([r[1] for r in rows]),
        "year": np.array([math.nan if r[2] is None else r[2] for r in rows], dtype=np.float64),
        "genres": obj([r[3] for r in rows]),
        "tags": obj([r[4] for r in rows]),
        "rating": np.array([math.nan if r[5] is None else r[5] for r in rows], dtype=np.float32),
        "votes": np.array([r[6] for r in rows], dtype=np.int32),
        "bayes": np.array([r[7] for r in rows], dtype=np.float32),
        "embed_text": obj([f"{r[1]}." for r in rows]),
    }


@pytest.fixture
def toy_catalog() -> Catalog:
    return Catalog(toy_columns())


@pytest.fixture
def soft_cfg() -> SoftConfig:
    return SoftConfig(beta=0.10, lam=0.30, mu=0.20)


@pytest.fixture
def runtime_cfg(soft_cfg: SoftConfig) -> RuntimeConfig:
    return RuntimeConfig(
        runtime_version="1.0",
        model_name="stub",
        index_backend="numpy",
        candidate_budget=200,
        rrf_k=60,
        score_round_decimals=6,
        soft=soft_cfg,
        metadata=MetadataConfig(tag_match_weight=0.5, bayes_m=10),
        mmr_lambda=0.7,
        seed=42,
        sha256="test",
    )
