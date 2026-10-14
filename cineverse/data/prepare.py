"""Build data/processed/catalog.parquet and the manifest from the raw MovieLens CSVs.

Steps P1–P9 and checks D1–D7. This is the only module that reads raw CSV (LR-6).
Spec: CineVerse_Dataset_and_Data_Pipeline_Specification §2–§4, §6;
CineVerse_Database_and_Data_Schemas §2–§3.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from cineverse.config import RegistryConfig, get_paths, load_registry_config, load_runtime_config

log = logging.getLogger(__name__)

PREPARE_VERSION = "1.0"
MANIFEST_VERSION = "1.0"
DATASET_NAME = "ml-latest-small"
NO_GENRES = "(no genres listed)"
TOP_TAGS = 20
YEAR_RE = re.compile(r"\s*\((\d{4})\)\s*$")
WHITESPACE_RE = re.compile(r"\s+")

REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "movies.csv": ("movieId", "title", "genres"),
    "ratings.csv": ("userId", "movieId", "rating", "timestamp"),
    "tags.csv": ("userId", "movieId", "tag", "timestamp"),
    "links.csv": ("movieId", "imdbId", "tmdbId"),
}

CATALOG_SCHEMA = pa.schema(
    [
        pa.field("movie_id", pa.int32(), nullable=False),
        pa.field("title", pa.string(), nullable=False),
        pa.field("year", pa.int16(), nullable=True),
        pa.field("genres", pa.list_(pa.string()), nullable=False),
        pa.field("tags", pa.list_(pa.string()), nullable=False),
        pa.field("rating", pa.float32(), nullable=True),
        pa.field("votes", pa.int32(), nullable=False),
        pa.field("bayes", pa.float32(), nullable=False),
        pa.field("embed_text", pa.string(), nullable=False),
    ]
)


class PrepareError(Exception):
    """Aborts preparation; the message starts with the failing check id (D1–D7, P2)."""


@dataclass
class PrepareReport:
    rows: int
    coverage: dict[str, float]
    orphans_dropped: dict[str, int]
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- P1, P2


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_csv(path: Path) -> pd.DataFrame:
    """Read every column as text (no NA guessing) so D1 can check names before typing."""
    if not path.is_file():
        raise PrepareError(f"D1: {path.name} not found in {path.parent}")
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    missing = [c for c in REQUIRED_COLUMNS[path.name] if c not in df.columns]
    if missing:
        raise PrepareError(f"D1: {path.name} is missing columns {missing}")
    return df


def _typed(df: pd.DataFrame, name: str, dtypes: dict[str, str]) -> pd.DataFrame:
    out = df.copy()
    for col, dtype in dtypes.items():
        try:
            if dtype == "Int64":
                out[col] = pd.to_numeric(out[col].replace("", None)).astype("Int64")
            else:
                out[col] = out[col].astype(dtype)
        except (ValueError, TypeError) as exc:
            raise PrepareError(f"P2: {name}.{col} cannot be read as {dtype} ({exc})") from exc
    return out


def load_raw(raw_dir: Path) -> dict[str, pd.DataFrame]:
    """P2 + D1: load the four CSVs with explicit dtypes."""
    movies = _typed(_read_csv(raw_dir / "movies.csv"), "movies.csv", {"movieId": "int32"})
    ratings = _typed(
        _read_csv(raw_dir / "ratings.csv"),
        "ratings.csv",
        {"userId": "int32", "movieId": "int32", "rating": "float32", "timestamp": "int64"},
    )
    tags = _typed(
        _read_csv(raw_dir / "tags.csv"),
        "tags.csv",
        {"userId": "int32", "movieId": "int32", "timestamp": "int64"},
    )
    links = _typed(
        _read_csv(raw_dir / "links.csv"),
        "links.csv",
        {"movieId": "int32", "imdbId": "int64", "tmdbId": "Int64"},
    )
    return {"movies": movies, "ratings": ratings, "tags": tags, "links": links}


# --------------------------------------------------------------------------- P3 checks


def validate(frames: dict[str, pd.DataFrame], registry: RegistryConfig) -> dict[str, int]:
    """D2–D5. Aborts on D2/D4/D5; drops orphan rows (D3) in place and returns their counts."""
    movies = frames["movies"]
    if not movies["movieId"].is_unique:
        dupes = movies.loc[movies["movieId"].duplicated(), "movieId"].head(5).tolist()
        raise PrepareError(f"D2: movieId not unique in movies.csv (e.g. {dupes})")

    known = set(movies["movieId"])
    orphans: dict[str, int] = {}
    for key in ("ratings", "tags", "links"):
        df = frames[key]
        mask = df["movieId"].isin(known)
        orphans[key] = int((~mask).sum())
        frames[key] = df[mask].reset_index(drop=True)

    ratings = frames["ratings"]["rating"]
    bad = ratings[(ratings < 0.5) | (ratings > 5.0)]
    if len(bad):
        raise PrepareError(f"D4: {len(bad)} ratings outside [0.5, 5.0] (e.g. {bad.iloc[0]})")

    allowed = set(registry.genres) | {NO_GENRES}
    seen = {g for s in movies["genres"] for g in s.split("|")}
    unknown = sorted(seen - allowed)
    if unknown:
        raise PrepareError(f"D5: genres not in registry: {unknown} (update config/registry.yaml)")
    return orphans


# --------------------------------------------------------------------------- P4–P8


def split_title(raw: str) -> tuple[str, int | None]:
    """P4: strip a trailing '(YYYY)' into year; earlier parentheses (alternative names) stay."""
    m = YEAR_RE.search(raw)
    if not m:
        return raw.strip(), None
    return raw[: m.start()].strip(), int(m.group(1))


def split_genres(raw: str) -> list[str]:
    """P5: pipe-separated genres; '(no genres listed)' -> []."""
    return [] if raw.strip() == NO_GENRES else [g for g in raw.split("|") if g]


def normalise_tag(raw: str) -> str:
    """P7: strip, lower-case, collapse whitespace."""
    return WHITESPACE_RE.sub(" ", raw.strip().lower())


def aggregate_ratings(
    movie_ids: pd.Series, ratings: pd.DataFrame, bayes_m: int
) -> tuple[pd.DataFrame, float]:
    """P6: mean rating, vote count and Bayesian rating per movie; returns (frame, global mean C)."""
    c = float(ratings["rating"].astype("float64").mean()) if len(ratings) else 0.0
    grouped = ratings.groupby("movieId")["rating"].agg(["mean", "count"])
    out = pd.DataFrame({"movieId": movie_ids.to_numpy()})
    out = out.merge(grouped, how="left", left_on="movieId", right_index=True)
    votes = out["count"].fillna(0).astype("int64")
    mean = out["mean"].astype("float64")
    bayes = (votes * mean.fillna(0.0) + bayes_m * c) / (votes + bayes_m)
    bayes = bayes.where(votes > 0, c)
    return (
        pd.DataFrame(
            {"movieId": out["movieId"], "rating": mean, "votes": votes, "bayes": bayes}
        ),
        c,
    )


def top_tags(tags: pd.DataFrame) -> dict[int, list[str]]:
    """P7: normalised tags per movie, top 20 by count then alphabetically."""
    if tags.empty:
        return {}
    t = tags.assign(tag=tags["tag"].map(normalise_tag))
    t = t[t["tag"] != ""]
    counts = t.groupby(["movieId", "tag"]).size().reset_index(name="n")
    counts = counts.sort_values(["movieId", "n", "tag"], ascending=[True, False, True])
    return {
        int(mid): grp["tag"].head(TOP_TAGS).tolist() for mid, grp in counts.groupby("movieId")
    }


def embed_text(title: str, genres: list[str], tags: list[str], display: dict[str, str]) -> str:
    """P8: '{title}. Genres: {g1, g2}. Tags: {t1, t2}.' (Tags part omitted when empty)."""
    text = f"{title}. Genres: {', '.join(display[g] for g in genres)}."
    if tags:
        text += f" Tags: {', '.join(tags)}."
    return text


def build_catalog(
    frames: dict[str, pd.DataFrame], registry: RegistryConfig, bayes_m: int
) -> pd.DataFrame:
    """P4–P8 over validated frames; returns the catalogue sorted by movie_id."""
    movies = frames["movies"].sort_values("movieId").reset_index(drop=True)
    parsed = movies["title"].map(split_title)
    agg, _ = aggregate_ratings(movies["movieId"], frames["ratings"], bayes_m)
    tag_map = top_tags(frames["tags"])
    display = dict(registry.genres)

    titles = [p[0] for p in parsed]
    genres = movies["genres"].map(split_genres).tolist()
    tags = [tag_map.get(int(mid), []) for mid in movies["movieId"]]
    return pd.DataFrame(
        {
            "movie_id": movies["movieId"].astype("int32"),
            "title": titles,
            "year": pd.array([p[1] for p in parsed], dtype="Int16"),
            "genres": genres,
            "tags": tags,
            "rating": agg["rating"].astype("float32"),
            "votes": agg["votes"].astype("int32"),
            "bayes": agg["bayes"].astype("float32"),
            "embed_text": [
                embed_text(t, g, tg, display) for t, g, tg in zip(titles, genres, tags)
            ],
        }
    )


def coverage(catalog: pd.DataFrame) -> dict[str, float]:
    n = max(len(catalog), 1)
    return {
        "year": round(float(catalog["year"].notna().sum()) / n, 4),
        "rating": round(float(catalog["rating"].notna().sum()) / n, 4),
        "tags": round(float(catalog["tags"].map(len).gt(0).sum()) / n, 4),
        "genres": round(float(catalog["genres"].map(len).gt(0).sum()) / n, 4),
    }


# --------------------------------------------------------------------------- P9 + manifest


def write_catalog(catalog: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(catalog, schema=CATALOG_SCHEMA, preserve_index=False)
    pq.write_table(table, path)


def _read_manifest(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _download_date(raw_dir: Path) -> str | None:
    """Date the snapshot arrived: mtime of the downloaded zip next to the raw folder, if kept."""
    zip_path = raw_dir.parent / f"{DATASET_NAME}.zip"
    if not zip_path.is_file():
        return None
    return datetime.fromtimestamp(zip_path.stat().st_mtime, tz=timezone.utc).date().isoformat()


def check_row_drift(
    previous: dict[str, Any] | None, rows: dict[str, int], tolerance: float = 0.2
) -> list[str]:
    """D7: warn when a file's row count moved more than ±20% since the previous build."""
    if not previous:
        return []
    old_files = previous.get("dataset", {}).get("files", {})
    warnings = []
    for name, n in rows.items():
        old = old_files.get(name, {}).get("rows")
        if isinstance(old, int) and old > 0 and abs(n - old) / old > tolerance:
            warnings.append(f"D7: {name} rows changed from {old} to {n} (> ±20%)")
    return warnings


def prepare(
    raw_dir: Path,
    catalog_path: Path,
    manifest_path: Path,
    registry: RegistryConfig,
    bayes_m: int,
) -> PrepareReport:
    """Run P1–P9 and write the catalogue and manifest. Raises PrepareError on abort checks."""
    files = {name: raw_dir / name for name in REQUIRED_COLUMNS}
    for name, p in files.items():
        if not p.is_file():
            raise PrepareError(f"D1: {name} not found in {raw_dir}")
    hashes = {name: _sha256(p) for name, p in files.items()}  # P1

    frames = load_raw(raw_dir)  # P2
    raw_rows = {
        "movies.csv": len(frames["movies"]),
        "ratings.csv": len(frames["ratings"]),
        "tags.csv": len(frames["tags"]),
        "links.csv": len(frames["links"]),
    }
    orphans = validate(frames, registry)  # P3
    catalog = build_catalog(frames, registry, bayes_m)  # P4–P8
    cov = coverage(catalog)

    warnings: list[str] = []
    if cov["year"] < 0.95:  # D6
        warnings.append(f"D6: only {cov['year']:.1%} of titles yield a year (< 95%)")
    previous = _read_manifest(manifest_path)
    warnings += check_row_drift(previous, raw_rows)  # D7
    for w in warnings:
        log.warning(w)

    write_catalog(catalog, catalog_path)  # P9

    manifest: dict[str, Any] = dict(previous or {})
    manifest["manifest_version"] = MANIFEST_VERSION
    manifest["dataset"] = {
        "name": DATASET_NAME,
        "downloaded": _download_date(raw_dir),
        "files": {n: {"sha256": hashes[n], "rows": raw_rows[n]} for n in REQUIRED_COLUMNS},
        "orphans_dropped": {"ratings": orphans["ratings"], "tags": orphans["tags"]},
    }
    manifest["catalog"] = {
        "rows": len(catalog),
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "prepare_version": PREPARE_VERSION,
        "coverage": cov,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return PrepareReport(rows=len(catalog), coverage=cov, orphans_dropped=orphans, warnings=warnings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the CineVerse catalogue from MovieLens.")
    paths = get_paths()
    parser.add_argument("--raw-dir", type=Path, default=paths.raw_dir)
    parser.add_argument("--out", type=Path, default=paths.catalog_path)
    parser.add_argument("--manifest", type=Path, default=paths.manifest_path)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    registry = load_registry_config()
    runtime = load_runtime_config()
    try:
        report = prepare(args.raw_dir, args.out, args.manifest, registry, runtime.metadata.bayes_m)
    except PrepareError as exc:
        log.error("prepare aborted: %s", exc)
        return 1
    log.info("catalogue rows: %d -> %s", report.rows, args.out)
    log.info("coverage: %s", report.coverage)
    log.info("orphans dropped: %s", report.orphans_dropped)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
