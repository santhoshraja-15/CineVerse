"""Read-only access to data/processed/catalog.parquet for runtime operators.

Spec: CineVerse_Recommendation_Engine_Specification §2.1; CineVerse_Database_and_Data_Schemas §2.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

REQUIRED_COLUMNS = (
    "movie_id", "title", "year", "genres", "tags", "rating", "votes", "bayes", "embed_text",
)
OPTIONAL_COLUMNS = ("runtime", "language")


class CatalogError(Exception):
    """The catalogue file is missing or does not match the schema."""


@dataclass(frozen=True, slots=True)
class MovieRecord:
    movie_id: int
    title: str
    year: int | None
    genres: tuple[str, ...]
    tags: tuple[str, ...]
    rating: float | None
    votes: int
    bayes: float
    embed_text: str


class Catalog:
    """Columnar catalogue. Rows are sorted by movie_id; every column is aligned with all_ids().

    Nullable numeric columns (year, rating, and optional runtime) are float arrays with NaN for
    unknown values, so constraint code can treat NaN as 'unknown => not satisfied'.
    """

    def __init__(self, columns: dict[str, np.ndarray]) -> None:
        ids = columns["movie_id"]
        if ids.size and not np.all(ids[1:] > ids[:-1]):
            raise CatalogError("movie_id must be unique and sorted ascending")
        self._columns = columns
        self._ids = ids
        self._row = {int(mid): i for i, mid in enumerate(ids)}

    @classmethod
    def load(cls, path: Path) -> Catalog:
        if not Path(path).is_file():
            raise CatalogError(
                f"catalogue not found: {path} (run python -m cineverse.data.prepare)"
            )
        table = pq.read_table(path)
        missing = [c for c in REQUIRED_COLUMNS if c not in table.column_names]
        if missing:
            raise CatalogError(f"catalogue {path} is missing columns {missing}")

        cols: dict[str, np.ndarray] = {}
        for name in table.column_names:
            arr = table.column(name)
            if name in ("genres", "tags"):
                values = arr.to_pylist()
                out = np.empty(len(values), dtype=object)
                out[:] = [tuple(v or ()) for v in values]
                cols[name] = out
            elif name in ("title", "embed_text", "language"):
                cols[name] = np.array(arr.to_pylist(), dtype=object)
            elif name == "movie_id":
                cols[name] = arr.to_numpy().astype(np.int64)
            elif name in ("year", "runtime"):
                cols[name] = np.array(
                    [np.nan if v is None else float(v) for v in arr.to_pylist()], dtype=np.float64
                )
            elif name == "rating":
                cols[name] = arr.to_numpy(zero_copy_only=False).astype(np.float32)
            else:
                cols[name] = arr.to_numpy(zero_copy_only=False)
        return cls(cols)

    def __len__(self) -> int:
        return int(self._ids.size)

    def all_ids(self) -> np.ndarray:
        """Sorted int64 movie ids."""
        return self._ids

    def column(self, name: str) -> np.ndarray:
        """Column values aligned with all_ids()."""
        if name not in self._columns:
            raise KeyError(f"unknown catalogue column {name!r}")
        return self._columns[name]

    def has_column(self, name: str) -> bool:
        return name in self._columns

    def rows(self, movie_ids: np.ndarray) -> np.ndarray:
        """Row positions for the given ids (KeyError for unknown ids)."""
        return np.fromiter((self._row[int(m)] for m in movie_ids), dtype=np.int64)

    def get(self, movie_id: int) -> MovieRecord:
        i = self._row[int(movie_id)]
        c = self._columns
        year = c["year"][i]
        rating = c["rating"][i]
        return MovieRecord(
            movie_id=int(c["movie_id"][i]),
            title=str(c["title"][i]),
            year=None if np.isnan(year) else int(year),
            genres=tuple(c["genres"][i]),
            tags=tuple(c["tags"][i]),
            rating=None if np.isnan(rating) else float(rating),
            votes=int(c["votes"][i]),
            bayes=float(c["bayes"][i]),
            embed_text=str(c["embed_text"][i]),
        )
