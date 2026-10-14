"""RuntimeContext and the RankedList value passed between runtime operators.

Spec: CineVerse_System_Architecture_and_Design §5.3; CineVerse_Recommendation_Engine_Specification
§2 (11.1).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from cineverse.compiler.ir import Capabilities
from cineverse.config import RuntimeConfig, get_paths, load_runtime_config
from cineverse.runtime.catalog import Catalog

if TYPE_CHECKING:
    from cineverse.runtime.embeddings import Encoder
    from cineverse.runtime.semantic_index import SemanticIndex

log = logging.getLogger(__name__)

RANK_KEYS = ("semantic_rank", "metadata_rank", "popularity_rank")


@dataclass(frozen=True)
class RankedList:
    ids: tuple[int, ...]  # rank = index + 1
    scores: tuple[float, ...]
    source: str  # "semantic" | "metadata" | "popularity" | "rrf" | "soft" | "mmr" | "topk"
    evidence: dict[int, dict[str, Any]] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.ids)

    @classmethod
    def empty(cls, source: str) -> RankedList:
        return cls((), (), source, {})

    def top(self, n: int) -> RankedList:
        """TOPK: first n entries, evidence kept."""
        ids = self.ids[:n]
        return RankedList(ids, self.scores[:n], "topk", {i: self.evidence.get(i, {}) for i in ids})


@dataclass
class RuntimeContext:
    catalog: Catalog
    index: SemanticIndex | None  # None => X201 path
    encoder: Encoder | None
    cfg: RuntimeConfig
    caps: Capabilities


def load_context(*, load_semantic: bool = True) -> RuntimeContext:
    """Load catalogue, config, encoder and index. A missing index or model sets
    `semantic_available=False` instead of failing (Architecture §6.2)."""
    paths = get_paths()
    cfg = load_runtime_config()
    catalog = Catalog.load(paths.catalog_path)
    index = encoder = None
    if load_semantic:
        from cineverse.runtime.embeddings import Encoder, ModelUnavailable
        from cineverse.runtime.semantic_index import IndexUnavailable, open_index

        try:
            encoder = Encoder(cfg.model_name)
            index = open_index(cfg.index_backend, paths.artifacts_dir, encoder)
        except (IndexUnavailable, ModelUnavailable) as exc:
            log.warning("semantic search unavailable: %s", exc)
            index = encoder = None
    caps = Capabilities(
        exact_search=cfg.index_backend in ("faiss_flat", "numpy"),
        semantic_available=index is not None,
        mmr_available=False,
    )
    return RuntimeContext(catalog=catalog, index=index, encoder=encoder, cfg=cfg, caps=caps)
