"""Temporary catalogue preview: browse the data model produced by task T04.

Not the CineVerse recommender UI (that is app/streamlit_app.py, task T28). It reads the prepared
catalogue and manifest only; nothing here compiles requests or ranks movies.
Run: streamlit run app/catalog_preview.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cineverse.runtime.catalog import Catalog, CatalogError

CATALOG_PATH = ROOT / "data" / "processed" / "catalog.parquet"
MANIFEST_PATH = ROOT / "artifacts" / "manifest.json"

# Database and Data Schemas §2 (CORE columns).
SCHEMA_DOC = [
    ("movie_id", "int32", "no", "MovieLens movieId; primary key; file sorted by it"),
    ("title", "string", "no", "Title without the year suffix"),
    ("year", "int16", "yes", 'From "(YYYY)"'),
    ("genres", "list<string>", "no", "Registry genre names; may be empty"),
    ("tags", "list<string>", "no", "Normalised, top 20; may be empty"),
    ("rating", "float32", "yes", "Mean rating"),
    ("votes", "int32", "no", "Count of ratings (0 if none)"),
    ("bayes", "float32", "no", "Bayesian rating (m = 10)"),
    ("embed_text", "string", "no", "Text that will be embedded (task T05)"),
]

PIPELINE = [
    ("P1", "Hash raw files (SHA-256)"),
    ("P2", "Load CSVs with explicit dtypes"),
    ("P3", "Validate (D1–D7)"),
    ("P4", "Split '(YYYY)' suffix into year"),
    ("P5", "Split genres on '|'"),
    ("P6", "Mean rating, votes, Bayesian rating"),
    ("P7", "Normalise tags; top 20"),
    ("P8", "Build embed_text"),
    ("P9", "Write catalog.parquet + manifest"),
]


@st.cache_resource(show_spinner="Loading catalogue…")
def load() -> tuple[pd.DataFrame, dict]:
    cat = Catalog.load(CATALOG_PATH)
    frame = pd.DataFrame(
        {
            "movie_id": cat.all_ids(),
            "title": cat.column("title"),
            "year": pd.array(
                [None if pd.isna(y) else int(y) for y in cat.column("year")], dtype="Int64"
            ),
            "genres": [list(g) for g in cat.column("genres")],
            "tags": [list(t) for t in cat.column("tags")],
            "rating": cat.column("rating").astype(float),
            "votes": cat.column("votes"),
            "bayes": cat.column("bayes").astype(float),
            "embed_text": cat.column("embed_text"),
        }
    )
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return frame, manifest


st.set_page_config(page_title="CineVerse · catalogue preview", page_icon="🎬", layout="wide")
st.title("CineVerse — catalogue preview")
st.caption(
    "Preview of the data model built in task T04. The recommender (compiler + runtime) is not "
    "built yet; its interface arrives in task T28."
)

try:
    df, manifest = load()
except (CatalogError, FileNotFoundError) as exc:
    st.error(f"Catalogue not available: {exc}")
    st.code("python -m cineverse.data.prepare", language="bash")
    st.stop()

cov = manifest["catalog"]["coverage"]
files = manifest["dataset"]["files"]
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Movies", f"{manifest['catalog']['rows']:,}")
c2.metric("Ratings", f"{files['ratings.csv']['rows']:,}")
c3.metric("Year known", f"{cov['year']:.1%}")
c4.metric("Rated", f"{cov['rating']:.1%}")
c5.metric("Tagged", f"{cov['tags']:.1%}")

browse, detail, model, pipeline, dist = st.tabs(
    ["Browse", "Movie detail", "Data model", "Pipeline & manifest", "Distributions"]
)

with browse:
    all_genres = sorted({g for gs in df["genres"] for g in gs})
    f1, f2, f3, f4 = st.columns([2, 2, 3, 1])
    query = f1.text_input("Title contains", "")
    genres = f2.multiselect("Has all genres", all_genres)
    years = df["year"].dropna()
    lo, hi = int(years.min()), int(years.max())
    year_range = f3.slider("Year", lo, hi, (lo, hi))
    min_votes = f4.number_input("Min votes", min_value=0, value=0, step=10)

    view = df
    if query:
        view = view[view["title"].str.contains(query, case=False, regex=False)]
    if genres:
        view = view[view["genres"].map(lambda gs: set(genres) <= set(gs))]
    if year_range != (lo, hi):
        view = view[view["year"].between(*year_range)]
    if min_votes:
        view = view[view["votes"] >= min_votes]

    st.caption(f"{len(view):,} of {len(df):,} movies · data browser only, no ranking")
    st.dataframe(
        view.drop(columns=["embed_text"]),
        hide_index=True,
        column_config={
            "genres": st.column_config.ListColumn("genres"),
            "tags": st.column_config.ListColumn("tags"),
            "rating": st.column_config.NumberColumn("rating", format="%.2f"),
            "bayes": st.column_config.NumberColumn("bayes", format="%.3f"),
        },
    )

with detail:
    options = df.sort_values("votes", ascending=False)
    labels = {
        int(r.movie_id): f"{r.title} ({'—' if pd.isna(r.year) else r.year}) · #{r.movie_id}"
        for r in options.itertuples()
    }
    choice = st.selectbox("Movie", list(labels), format_func=labels.__getitem__)
    rec = df[df["movie_id"] == choice].iloc[0]
    left, right = st.columns([1, 1])
    with left:
        st.subheader(rec["title"])
        st.write(f"**Year:** {'unknown' if pd.isna(rec['year']) else rec['year']}")
        st.write(f"**Genres:** {', '.join(rec['genres']) or '—'}")
        st.write(f"**Tags:** {', '.join(rec['tags']) or '—'}")
        rating = "unrated" if pd.isna(rec["rating"]) else f"{rec['rating']:.2f}★"
        st.write(f"**Mean rating:** {rating} from {rec['votes']} ratings")
        st.write(f"**Bayesian rating:** {rec['bayes']:.3f}")
    with right:
        st.markdown("**embed_text** (what the encoder will see in T05)")
        st.code(rec["embed_text"], language=None, wrap_lines=True)
        st.markdown("**MovieRecord** (`Catalog.get`)")
        st.json({k: (None if pd.isna(v) else v) if not isinstance(v, list) else v
                 for k, v in rec.drop("embed_text").to_dict().items()})

with model:
    st.markdown("`data/processed/catalog.parquet` — Database and Data Schemas §2")
    st.dataframe(
        pd.DataFrame(SCHEMA_DOC, columns=["column", "arrow type", "nullable", "rule"]),
        hide_index=True,
    )
    st.markdown("Runtime access — `cineverse/runtime/catalog.py`")
    st.code(
        "Catalog.load(path) -> Catalog\n"
        "Catalog.all_ids() -> np.ndarray      # sorted int64\n"
        "Catalog.get(movie_id) -> MovieRecord\n"
        "Catalog.column(name) -> np.ndarray   # aligned with all_ids(); NaN = unknown",
        language="python",
    )

with pipeline:
    st.markdown("`python -m cineverse.data.prepare` — Dataset Spec §3")
    st.dataframe(pd.DataFrame(PIPELINE, columns=["step", "operation"]), hide_index=True)
    st.markdown("`artifacts/manifest.json`")
    st.json(manifest, expanded=2)

with dist:
    g1, g2 = st.columns(2)
    genre_counts = (
        df["genres"].explode().dropna().value_counts().rename_axis("genre").reset_index()
    )
    g1.markdown("**Movies per genre**")
    g1.bar_chart(genre_counts, x="genre", y="count", horizontal=True, sort="-count")
    decade = (df["year"].dropna() // 10 * 10).astype(int).astype(str) + "s"
    g2.markdown("**Movies per decade**")
    g2.bar_chart(decade.value_counts().sort_index().rename_axis("decade").reset_index(),
                 x="decade", y="count")
    rated = df["rating"].dropna().round(1)
    st.markdown("**Mean rating (rated movies)**")
    st.bar_chart(rated.value_counts().sort_index().rename_axis("rating").reset_index(),
                 x="rating", y="count")

st.caption(
    f"Dataset {manifest['dataset']['name']} · movies.csv sha256 "
    f"{files['movies.csv']['sha256'][:12]}… · catalogue built {manifest['catalog']['built']}"
)
