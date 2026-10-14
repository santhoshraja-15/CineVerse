"""Frontend mockup: how the finished CineVerse website (UI/UX Spec §2) will look and behave.

The compiler is not built yet. This page replays the expected outputs of the 25 worked examples in
docs/CineVerse_Example_Requests_and_Expected_Outputs.json (tokens, diagnostics, IR, rules fired,
programs). Result cards use real catalogue movies that pass the example's hard constraints, in a
stand-in order; they are NOT CineVerse rankings. Replaced by app/streamlit_app.py in task T28.
"""

from __future__ import annotations

import difflib
import html
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cineverse.runtime.catalog import Catalog, CatalogError, MovieRecord

EXAMPLES_PATH = ROOT / "docs" / "CineVerse_Example_Requests_and_Expected_Outputs.json"
CATALOG_PATH = ROOT / "data" / "processed" / "catalog.parquet"
MANIFEST_PATH = ROOT / "artifacts" / "manifest.json"

# Frontend Spec §7 (severity, message template).
DIAGNOSTICS = {
    "L001": ("INFO", "Ignored character '{ch}'"),
    "P001": ("WARNING", "Could not understand '{text}'; skipped"),
    "P002": ("WARNING", "Number {n} has no meaning here"),
    "S101": ("INFO", "'{word}' is not a known genre; used as a description"),
    "S102": ("ERROR", "Cannot tell what '{text}' refers to (year, rating, votes or runtime?)"),
    "S103": ("ERROR", "'{op}' cannot be used with {field}"),
    "S104": ("ERROR", "{value} is outside the range of {field} ({lo}–{hi})"),
    "S105": ("WARNING", "{field} is not available in this catalogue; '{text}' was not applied"),
    "S106": ("WARNING", "'{text}' cannot be checked exactly; applied as a preference"),
    "S107": ("ERROR", "{genre} is both required and excluded"),
    "S108": ("ERROR", "No {field} satisfies all conditions"),
    "S109": ("WARNING", "Number of results limited to {n}"),
    "S110": ("WARNING", "Preference for {genre} overridden by a strict condition"),
    "S111": ("ERROR", "Nothing to recommend from; add a genre, mood or condition"),
    "S112": ("INFO", "Converted {from} to {to}"),
    "S113": ("ERROR", "Request is empty or longer than {max} characters"),
    "S114": ("WARNING", "'only … or …' cannot be applied strictly; used as preferences"),
    "X201": ("WARNING", "Semantic search unavailable; results use metadata only"),
    "X202": ("INFO", "No movie satisfies all strict conditions"),
}
SEVERITY_ICON = {"ERROR": "⛔", "WARNING": "⚠️", "INFO": "ℹ️"}

TOKEN_COLOURS = {
    "GENRE": "#4ade80", "DESCRIPTOR": "#60a5fa", "WORD": "#d6a77a", "NEG_HARD": "#f87171",
    "NEG_SOFT": "#fb923c", "HEDGE": "#fbbf24", "STRICT": "#c084fc", "CMP": "#22d3ee",
    "NUMBER": "#22d3ee", "DECADE": "#22d3ee", "UNIT": "#22d3ee", "FIELD": "#22d3ee",
    "BETWEEN": "#22d3ee", "TO": "#22d3ee", "LIMIT": "#94a3b8", "ITEM": "#94a3b8",
    "DIVERSE": "#94a3b8", "SEP": "#64748b", "OR": "#64748b", "FILLER": "#475569",
}
TOKEN_MEANING = {
    "GENRE": "a known genre", "DESCRIPTOR": "a mood or theme",
    "WORD": "an unknown word, kept as text",
    "NEG_HARD": "strict negation", "NEG_SOFT": "soft negation", "HEDGE": "softener",
    "STRICT": "makes the next genre required", "CMP": "comparison", "NUMBER": "number",
    "DECADE": "decade", "UNIT": "unit", "FIELD": "field name", "BETWEEN": "range",
    "LIMIT": "result count", "ITEM": "'movies'", "DIVERSE": "diversity", "SEP": "separator",
    "OR": "alternative", "FILLER": "ignored filler word",
}
GENRE_STYLE = {
    "Action": ("💥", "#ef4444"), "Adventure": ("🧭", "#f59e0b"), "Animation": ("🎨", "#ec4899"),
    "Children": ("🧸", "#f472b6"), "Comedy": ("😂", "#eab308"), "Crime": ("🕵️", "#64748b"),
    "Documentary": ("🎥", "#14b8a6"), "Drama": ("🎭", "#8b5cf6"), "Fantasy": ("🐉", "#a855f7"),
    "Film-Noir": ("🌃", "#334155"), "Horror": ("👻", "#7f1d1d"), "IMAX": ("🎞️", "#0ea5e9"),
    "Musical": ("🎵", "#d946ef"), "Mystery": ("🔍", "#6366f1"), "Romance": ("💕", "#f43f5e"),
    "Sci-Fi": ("🚀", "#06b6d4"), "Thriller": ("🔪", "#b91c1c"), "War": ("⚔️", "#78716c"),
    "Western": ("🤠", "#c2410c"),
}
OPCODE_MEANING = {
    "SCAN": "Start from every movie in the catalogue",
    "MASK": "Keep only movies that pass every strict (hard) condition — computed once, shared",
    "SEM_SEARCH": "Meaning-based search: embed the text, find the closest movies (exact FAISS)",
    "META_SEARCH": "Count genre matches and tag matches for your words",
    "POP_RANK": "No positive wish given: rank by Bayesian rating",
    "FILTER_LIST": "Apply strict conditions after searching, keep order, cut to 200",
    "RRF": "Merge the ranked lists with Reciprocal Rank Fusion (k = 60)",
    "SOFT": "+0.10 per wanted match, −0.30 per unwanted match, −0.20 per missed soft condition",
    "TOPK": "Keep the requested number of results",
    "EXPLAIN": "Write reasons from recorded evidence only",
    "RET": "Return the results",
}
STAGES = [
    ("✍️", "Input", "Your sentence, 1–300 characters"),
    ("🔤", "Tokens", "Lexer: words become typed tokens with exact positions"),
    ("🌳", "AST", "Parser: tokens become clauses"),
    ("🧠", "Semantic", "Checks meaning: field inference, hard vs soft, contradictions"),
    ("📦", "IR", "One canonical, hashable form of the meaning"),
    ("🗺️", "Plan", "A dataflow of search, filter, fuse and score operators"),
    ("⚙️", "Program", "Numbered SSA instructions the engine executes"),
    ("🎬", "Results", "Ranked movies with reasons"),
]
# Project report §5.4 (only EX01 has a published AST).
EX01_AST = """RequestNode
├── PreferenceClause(modifier=NONE)            [0, 25)
│   ├── DescriptorTerm("thoughtful")           [0, 10)
│   ├── GenreTerm("sci-fi" → Sci-Fi)           [11, 17)
│   └── GenreTerm("mystery" → Mystery)         [18, 25)
├── ConstraintClause(field=None, op=GT,        [26, 36)
│       values=[NumberNode(2010)])
├── ExclusionClause(strength=SOFT)             [38, 52)
│   └── GenreTerm("romance" → Romance)         [45, 52)
└── LimitClause(n=5)                           [54, 59)"""
TOUR = [
    ("EX01", "Plain English in, explained results out"),
    ("EX03", "'no romance' — a hard exclusion removes movies"),
    ("EX18", "'ideally no horror' — the same word, softened, only penalises"),
    ("EX07", "'under 2 hours' — honest: the data has no runtime (S105)"),
    ("EX08", "A contradiction stops compilation before anything runs"),
    ("EX23", "Paraphrases compile to the same meaning (compare with EX24)"),
]
TOKEN_RE = re.compile(r"^([A-Z_]+)\((.*?)\)(?:\[(\d+),(\d+)\))?$")
INSTR_RE = re.compile(r"^(?:%(\w+) = )?(\w+)\s*(.*)$")
REG_RE = re.compile(r"%(\w+)")

CSS = """
<style>
.block-container {padding-top: 1.6rem; max-width: 1250px;}
.cv-hero {background: radial-gradient(circle at 15% 20%, #7c3aed55 0, transparent 45%),
  radial-gradient(circle at 85% 30%, #06b6d455 0, transparent 40%),
  linear-gradient(135deg, #0b0b14 0%, #1a1033 55%, #0b2235 100%);
  border: 1px solid #2b2b40; border-radius: 22px; padding: 30px 34px 26px; margin-bottom: 14px;}
.cv-hero h1 {font-size: 2.6rem; margin: 0; letter-spacing: -0.02em;
  background: linear-gradient(90deg, #f5f3ff, #c4b5fd 45%, #67e8f9);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;}
.cv-hero p {color: #cbd5e1; margin: 6px 0 0; font-size: 1.05rem;}
.cv-mock {display:inline-block; margin-top:12px; padding:3px 10px; border-radius:999px;
  background:#f59e0b22; color:#fbbf24; border:1px solid #f59e0b55; font-size:.78rem;}
.cv-tokens {font-size: 1.35rem; line-height: 3.1rem; padding: 10px 14px; background:#11111a;
  border:1px solid #26263a; border-radius: 14px;}
.cv-tok {position: relative; padding: 2px 3px; border-bottom: 3px solid; border-radius: 3px;}
.cv-tok sub {position:absolute; left:0; top:1.9rem; font-size:.55rem; white-space:nowrap;
  letter-spacing:.04em;}
.cv-flow {display:flex; gap:6px; flex-wrap:wrap; align-items:center; margin: 6px 0 4px;}
.cv-stage {background:#151522; border:1px solid #2b2b40; border-radius:12px; padding:7px 11px;
  font-size:.82rem; color:#e2e8f0;}
.cv-stage.done {border-color:#7c3aed; box-shadow:0 0 0 1px #7c3aed55 inset;}
.cv-stage.stop {border-color:#ef4444; color:#fca5a5;}
.cv-stage.skip {opacity:.35;}
.cv-arrow {color:#64748b;}
.cv-card {border-radius:16px; overflow:hidden; background:#12121c; border:1px solid #26263a;
  transition: transform .15s ease, border-color .15s ease; height: 100%;}
.cv-card:hover {transform: translateY(-3px); border-color:#7c3aed;}
.cv-poster {height:150px; position:relative; padding:12px 14px; display:flex;
  flex-direction:column; justify-content:space-between;}
.cv-rank {align-self:flex-start; background:#000a; color:#fff; border-radius:10px;
  padding:2px 9px; font-weight:700; font-size:.85rem;}
.cv-emoji {position:absolute; right:12px; top:8px; font-size:2.6rem; opacity:.9;}
.cv-title {color:#fff; font-weight:800; font-size:1.08rem; line-height:1.25;
  text-shadow:0 2px 8px #000c;}
.cv-body {padding:10px 14px 12px;}
.cv-meta {color:#94a3b8; font-size:.8rem; margin-bottom:6px;}
.cv-chip {display:inline-block; padding:1px 8px; border-radius:999px; font-size:.7rem;
  margin:0 3px 3px 0; background:#23233a; color:#cbd5e1;}
.cv-chip.hard {background:#14532d; color:#bbf7d0;}
.cv-chip.pen {background:#7c2d12; color:#fed7aa;}
.cv-reason {color:#e2e8f0; font-size:.8rem; margin:3px 0;}
.cv-stars {color:#fbbf24; letter-spacing:1px;}
.cv-diff-del {background:#7f1d1d55; color:#fecaca; text-decoration: line-through;}
.cv-diff-add {background:#14532d66; color:#bbf7d0;}
.cv-code {font-family: ui-monospace, Consolas, monospace; font-size:.8rem; white-space:pre;
  background:#0d0d14; border:1px solid #26263a; border-radius:12px; padding:10px 12px;
  overflow-x:auto;}
.cv-hash {font-family: ui-monospace, Consolas, monospace; font-size:1.05rem; color:#67e8f9;}
</style>
"""


# --------------------------------------------------------------------------- data


@st.cache_resource(show_spinner="Loading examples and catalogue…")
def load() -> tuple[dict[str, dict], Catalog, dict]:
    data = json.loads(EXAMPLES_PATH.read_text(encoding="utf-8"))
    examples = {ex["id"]: ex for ex in data["examples"]}
    catalog = Catalog.load(CATALOG_PATH)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return examples, catalog, manifest


def parse_token(text: str) -> dict:
    m = TOKEN_RE.match(text)
    if not m:
        return {"type": "?", "lexeme": text, "value": "", "span": None}
    ttype, body, start, end = m.groups()
    lexeme, _, value = body.partition("->")
    return {
        "type": ttype,
        "lexeme": lexeme,
        "value": value.strip("'") if value else lexeme,
        "span": (int(start), int(end)) if start is not None else None,
    }


def token_html(text: str, tokens: list[dict]) -> str:
    out, pos = [], 0
    for t in sorted((t for t in tokens if t["span"]), key=lambda t: t["span"][0]):
        s, e = t["span"]
        colour = TOKEN_COLOURS.get(t["type"], "#94a3b8")
        tip = html.escape(f"{t['type']}: {TOKEN_MEANING.get(t['type'], '')} → {t['value']}")
        out.append(html.escape(text[pos:s]))
        out.append(
            f'<span class="cv-tok" style="border-color:{colour}" title="{tip}">'
            f'{html.escape(text[s:e])}<sub style="color:{colour}">{t["type"]}</sub></span>'
        )
        pos = e
    out.append(html.escape(text[pos:]))
    return f'<div class="cv-tokens">{"".join(out)}</div>'


def flow_html(ok: bool, reached: int | None = None) -> str:
    """Pipeline strip. When compilation stops, stages after Semantic are greyed out."""
    parts = []
    for i, (icon, name, _) in enumerate(STAGES):
        cls = "done"
        if not ok and i == 3:
            cls = "stop"
        elif not ok and i > 3:
            cls = "skip"
        if reached is not None and i > reached:
            cls = "skip"
        parts.append(f'<span class="cv-stage {cls}">{icon} {name}</span>')
        if i < len(STAGES) - 1:
            parts.append('<span class="cv-arrow">➜</span>')
    return f'<div class="cv-flow">{"".join(parts)}</div>'


def plan_dot(program: list[str], optimized: bool) -> str:
    lines = [
        "digraph plan {",
        'rankdir=LR; bgcolor="transparent";',
        (
            'node [shape=box, style="rounded,filled", fillcolor="#1e1b3a", color="#7c3aed", '
            'fontcolor="#f1f5f9", fontname="Helvetica"];'
        ),
        'edge [color="#94a3b8"];',
    ]
    for line in program:
        m = INSTR_RE.match(line)
        if not m:
            continue
        dest, op, rest = m.groups()
        node = dest or "ret"
        fill = "#9a3412" if optimized and op == "MASK" else "#1e1b3a"
        lines.append(f'"{node}" [label="%{node}\\n{op}", fillcolor="{fill}"];')
        for src in dict.fromkeys(REG_RE.findall(rest)):
            lines.append(f'"{src}" -> "{node}";')
    lines.append("}")
    return "\n".join(lines)


def program_diff_html(before: list[str], after: list[str]) -> str:
    rows = []
    for op, line in (
        (d[0], d[2:]) for d in difflib.ndiff(before, after) if d[:1] in (" ", "-", "+")
    ):
        safe = html.escape(line)
        if op == "-":
            rows.append(f'<div class="cv-diff-del">− {safe}</div>')
        elif op == "+":
            rows.append(f'<div class="cv-diff-add">+ {safe}</div>')
        else:
            rows.append(f"<div>&nbsp; {safe}</div>")
    return f'<div class="cv-code">{"".join(rows)}</div>'


# --------------------------------------------------------------------------- stand-in results


def eligible_mask(catalog: Catalog, constraints: list[dict]) -> np.ndarray:
    """Hard constraints on the real catalogue; unknown values fail (Engine Spec §11.5)."""
    mask = np.ones(len(catalog), dtype=bool)
    genres = catalog.column("genres")
    ops = {">=": np.greater_equal, "<=": np.less_equal, ">": np.greater, "<": np.less}
    for c in constraints:
        if c["strictness"] != "hard":
            continue
        if c["field"] == "genre":
            has = np.fromiter((c["value"] in g for g in genres), dtype=bool, count=len(catalog))
            mask &= has if c["op"] == "HAS" else ~has
        else:
            col = catalog.column(c["field"]).astype(float)
            with np.errstate(invalid="ignore"):
                mask &= ~np.isnan(col) & ops[c["op"]](col, float(c["value"]))
    return mask


def stand_in_results(catalog: Catalog, ir: dict) -> tuple[list[dict], int]:
    """Eligible movies ordered by (#positive matches − #negative matches, bayes, id)."""
    mask = eligible_mask(catalog, ir["constraints"])
    rows = np.flatnonzero(mask)
    pos = [p for p in ir["preferences"] if p["polarity"] == 1]
    neg = [p for p in ir["preferences"] if p["polarity"] == -1]
    hard = [c for c in ir["constraints"] if c["strictness"] == "hard"]
    hard_has = [c["value"] for c in hard if c["op"] == "HAS"]
    soft = [c for c in ir["constraints"] if c["strictness"] == "soft"]

    def matches(prefs: list[dict], genres: tuple, tags: tuple) -> list[str]:
        hit = []
        for p in prefs:
            is_genre = p["kind"] == "genre" and p["value"] in genres
            is_tag = p["kind"] == "text" and any(p["value"] in t for t in tags)
            if is_genre or is_tag:
                hit.append(p["value"])
        return hit

    genres, tags = catalog.column("genres"), catalog.column("tags")
    bayes, ids = catalog.column("bayes"), catalog.all_ids()
    scored = []
    for i in rows:
        good = matches(pos, genres[i], tags[i]) + [g for g in hard_has if g in genres[i]]
        bad = matches(neg, genres[i], tags[i])
        scored.append((-(len(good) - len(bad)), -round(float(bayes[i]), 6), int(ids[i]), good, bad))
    scored.sort(key=lambda s: s[:3])

    out = []
    for *_, mid, good, bad in scored[: ir["output"]["limit"]]:
        rec = catalog.get(mid)
        reasons, hard_ok, penalties = [], [], []
        genre_hits = list(dict.fromkeys(g for g in good if g in rec.genres))
        if genre_hits:
            reasons.append(f"Genres {' and '.join(genre_hits)} match your request")
        for term in (g for g in good if g not in rec.genres):
            tag = next(t for t in rec.tags if term in t)
            reasons.append(f"Tagged '{tag}', matching '{term}'")
        year_bounds = [f"{c['op']} {c['value']}" for c in hard if c["field"] == "year"]
        if year_bounds and rec.year is not None:
            hard_ok.append(f"year {rec.year} ({', '.join(year_bounds)})")
        for c in hard:
            if c["field"] == "rating" and rec.rating is not None:
                hard_ok.append(f"rating {rec.rating:.1f} ({c['op']} {c['value']})")
            elif c["field"] == "votes":
                hard_ok.append(f"{rec.votes} ratings ({c['op']} {c['value']})")
            elif c["op"] == "NOT_HAS":
                hard_ok.append(f"not {c['value']}")
            elif c["op"] == "HAS":
                hard_ok.append(f"is {c['value']}")
        for b in bad:
            penalties.append(f"has {b} (−0.30)")
        for c in soft:
            if c["field"] == "year" and (
                rec.year is None or not eval_bound(rec.year, c["op"], c["value"])
            ):
                penalties.append(f"year {rec.year} misses soft {c['op']} {c['value']} (−0.20)")
        if rec.rating is not None:
            reasons.append(f"Highly rated: {rec.rating:.1f}★ from {rec.votes} ratings")
        out.append(
            {"rec": rec, "reasons": reasons[:4], "hard": hard_ok, "penalties": penalties,
             "good": good, "bad": bad}
        )
    return out, int(mask.sum())


def eval_bound(value: float, op: str, bound: float) -> bool:
    return {">=": value >= bound, "<=": value <= bound, ">": value > bound, "<": value < bound}[op]


def stars(rating: float | None) -> str:
    if rating is None:
        return '<span style="color:#64748b">unrated</span>'
    full = round(rating)
    return f'<span class="cv-stars">{"★" * full}{"☆" * (5 - full)}</span> {rating:.1f}'


def card_html(rank: int, item: dict) -> str:
    rec: MovieRecord = item["rec"]
    colours = [GENRE_STYLE.get(g, ("🎬", "#475569"))[1] for g in rec.genres[:2]] or ["#475569"]
    if len(colours) == 1:
        colours.append("#0b0b14")
    emoji = GENRE_STYLE.get(rec.genres[0], ("🎬", ""))[0] if rec.genres else "🎬"
    chips = "".join(f'<span class="cv-chip">{html.escape(g)}</span>' for g in rec.genres[:4])
    chips += "".join(
        f'<span class="cv-chip hard">✓ {html.escape(h)}</span>' for h in item["hard"]
    )
    chips += "".join(
        f'<span class="cv-chip pen">{html.escape(p)}</span>' for p in item["penalties"]
    )
    reasons = "".join(f'<div class="cv-reason">• {html.escape(r)}</div>' for r in item["reasons"])
    year = rec.year if rec.year is not None else "—"
    return (
        f'<div class="cv-card"><div class="cv-poster" style="background:linear-gradient(135deg,'
        f'{colours[0]} 0%, {colours[1]} 100%)"><span class="cv-rank">#{rank}</span>'
        f'<span class="cv-emoji">{emoji}</span>'
        f'<div class="cv-title">{html.escape(rec.title)}</div></div>'
        f'<div class="cv-body"><div class="cv-meta">{year} · {stars(rec.rating)} · '
        f"{rec.votes} ratings</div>{chips}{reasons}</div></div>"
    )


@st.dialog("Why this movie?", width="large")
def explain_dialog(item: dict, request: str) -> None:
    rec: MovieRecord = item["rec"]
    st.markdown(f"### {rec.title} ({rec.year if rec.year is not None else '—'})")
    st.caption(f"for: “{request}”")
    left, right = st.columns(2)
    with left:
        st.markdown("**Strict conditions checked**")
        for h in item["hard"] or ["none in this request"]:
            st.markdown(f"- ✅ {h}")
        st.markdown("**Your wishes it matches**")
        for g in item["good"] or ["—"]:
            st.markdown(f"- 💚 {g}")
        st.markdown("**Soft penalties**")
        for p in item["penalties"] or ["none"]:
            st.markdown(f"- 🔻 {p}")
    with right:
        st.markdown("**Catalogue evidence**")
        st.json(
            {"movie_id": rec.movie_id, "genres": list(rec.genres), "tags": list(rec.tags),
             "rating": rec.rating, "votes": rec.votes, "bayes": round(rec.bayes, 3)}
        )
        st.markdown("**Text the encoder sees**")
        st.code(rec.embed_text, language=None, wrap_lines=True)
    st.caption("In the finished app every line here comes from the execution trace (FR-17).")


# --------------------------------------------------------------------------- page

st.set_page_config(page_title="CineVerse · website preview", page_icon="🎬", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

try:
    examples, catalog, manifest = load()
except (CatalogError, FileNotFoundError) as exc:
    st.error(f"Needs the prepared catalogue and docs: {exc}")
    st.stop()

if "request" not in st.session_state:
    st.session_state.request = examples["EX01"]["text"]
if "animated" not in st.session_state:
    st.session_state.animated = set()


def load_example(ex_id: str) -> None:
    st.session_state.request = examples[ex_id]["text"]


# Sidebar: guided demo.
with st.sidebar:
    st.markdown("### 🎓 Guided demo")
    st.caption("The viva walkthrough (Runbook §6). Click a step to load it.")
    for i, (ex_id, note) in enumerate(TOUR, 1):
        st.button(f"{i}. {examples[ex_id]['text']}", key=f"tour_{ex_id}", help=note,
                  on_click=load_example, args=(ex_id,), width="stretch")
        st.caption(note)
    st.divider()
    st.markdown("**Token colours**")
    st.markdown(
        " ".join(
            f'<span style="color:{TOKEN_COLOURS[t]};font-size:.8rem">■ {t}</span>'
            for t in ("GENRE", "DESCRIPTOR", "WORD", "NEG_HARD", "NEG_SOFT", "HEDGE", "STRICT",
                      "CMP")
        ),
        unsafe_allow_html=True,
    )

st.markdown(
    '<div class="cv-hero"><h1>🎬 CineVerse</h1>'
    "<p>Describe the movie you want in plain English. A compiler turns your words into a "
    "checked, optimized plan — and every result tells you why.</p>"
    '<span class="cv-mock">🧪 Preview · replays the 25 spec examples · live compiler arrives '
    "in T20/T28</span></div>",
    unsafe_allow_html=True,
)

col_in, col_opt = st.columns([5, 1], vertical_alignment="bottom")
text = col_in.text_input(
    "What do you feel like watching?", key="request", max_chars=300,
    placeholder="thoughtful sci-fi mystery after 2010, little romance, top 5",
)
optimize = col_opt.toggle("⚡ Optimizer", value=True, help="Same results, less work.")

def on_pill() -> None:
    choice = st.session_state.pill
    if choice:
        load_example(choice)
    st.session_state.pill = None


st.pills(
    "Try one", list(examples), format_func=lambda k: examples[k]["text"],
    key="pill", selection_mode="single", on_change=on_pill,
)

match = next(
    (e for e in examples.values() if e["text"].strip().lower() == text.strip().lower()), None
)
if match is None:
    st.info(
        "This preview can only replay the 25 spec examples; the finished site compiles any "
        "sentence. Closest examples:", icon="🔎",
    )
    close = difflib.get_close_matches(text.lower(), [e["text"] for e in examples.values()],
                                      n=3, cutoff=0.0)
    for c in close:
        ex_id = next(k for k, e in examples.items() if e["text"] == c)
        st.button(c, key=f"close_{ex_id}", on_click=load_example, args=(ex_id,))
    st.stop()

exp = match["expected"]
tokens = [parse_token(t) for t in exp["tokens"]]

# "Compiling" animation, once per request (visual only: no timings are claimed).
if match["id"] not in st.session_state.animated:
    with st.status("Compiling your request…", expanded=True) as status:
        bar = st.progress(0.0)
        for i, (icon, name, what) in enumerate(STAGES[1:], 1):
            if not exp["ok"] and i > 3:
                break
            st.write(f"{icon} **{name}** — {what}")
            bar.progress(i / (len(STAGES) - 1))
            time.sleep(0.18)
        if exp["ok"]:
            status.update(label="Compiled and executed ✓", state="complete", expanded=False)
        else:
            status.update(label="Stopped at semantic analysis ⛔", state="error", expanded=False)
    st.session_state.animated.add(match["id"])

st.markdown(flow_html(exp["ok"]), unsafe_allow_html=True)
st.markdown(token_html(match["text"], tokens), unsafe_allow_html=True)
st.caption("Hover a word to see how the lexer typed it.")

for code in exp["diagnostics"]:
    sev, template = DIAGNOSTICS[code]
    show = {"ERROR": st.error, "WARNING": st.warning, "INFO": st.info}[sev]
    show(f"**{code}** · {template}", icon=SEVERITY_ICON[sev])
if match.get("notes"):
    st.caption(f"💡 {match['notes']}")

results_tab, compiler_tab, compare_tab = st.tabs(
    ["🎬 Results", "🛠️ How it was compiled", "⚖️ Compare two requests"]
)

with results_tab:
    if not exp["ok"]:
        st.error(
            "Compilation stopped before planning, so nothing was searched. "
            "Fix the highlighted condition and try again.", icon="⛔",
        )
    else:
        results, eligible = stand_in_results(catalog, exp["ir"])
        hard_n = sum(c["strictness"] == "hard" for c in exp["ir"]["constraints"])
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Movies in catalogue", f"{len(catalog):,}")
        m2.metric("Pass strict conditions", f"{eligible:,}", help=f"{hard_n} hard condition(s)")
        m3.metric("Showing", len(results))
        m4.metric("Rules applied", len(exp.get("rules_fired", [])),
                  help="\n".join(exp.get("rules_fired", [])))
        st.caption(
            "Stand-in order: matches first, then Bayesian rating. Real CineVerse scores "
            "(semantic + metadata fused with RRF, then soft scoring) replace this in T19–T20."
        )
        per_row = 3 if len(results) <= 12 else 4
        for start in range(0, len(results), per_row):
            cols = st.columns(per_row)
            for col, (rank, item) in zip(
                cols, enumerate(results[start:start + per_row], start + 1), strict=False
            ):
                with col:
                    st.markdown(card_html(rank, item), unsafe_allow_html=True)
                    if st.button("Why this movie?", key=f"why_{match['id']}_{rank}",
                                 width="stretch"):
                        explain_dialog(item, match["text"])
        st.caption("Expected by the spec: " + "; ".join(exp["result_properties"]))

with compiler_tab:
    stage_names = [f"{icon} {name}" for icon, name, _ in STAGES[1:7]]
    chosen = st.segmented_control("Inspect a stage", stage_names, default=stage_names[0],
                                  key=f"stage_{match['id']}") or stage_names[0]
    name = chosen.split(" ", 1)[1]
    st.caption(next(w for _, n, w in STAGES if n == name))

    if name == "Tokens":
        st.dataframe(
            pd.DataFrame(
                [{"type": t["type"], "lexeme": t["lexeme"], "value": t["value"],
                  "meaning": TOKEN_MEANING.get(t["type"], ""),
                  "span": "—" if t["span"] is None else f"[{t['span'][0]}, {t['span'][1]})"}
                 for t in tokens]
            ),
            hide_index=True, width="stretch",
        )
    elif name == "AST":
        if match["id"] == "EX01":
            st.code(EX01_AST, language=None)
            st.caption("From the project report §5.4. Every request gets this tree once the "
                       "parser exists (T12).")
        else:
            st.info("The parse tree for this request appears once the parser exists (T12). "
                    "Load EX01 from the guided demo to see a published example.", icon="🌳")
    elif name == "Semantic":
        if exp["ok"]:
            ir = exp["ir"]
            rows = [{"what": f"{p['kind']} {p['value']}", "strictness": "soft",
                     "effect": "boost +0.10" if p["polarity"] == 1 else "penalty −0.30"}
                    for p in ir["preferences"]]
            rows += [{"what": f"{c['field']} {c['op']} {c['value']}", "strictness": c["strictness"],
                      "effect": "removes non-matching movies" if c["strictness"] == "hard"
                      else "penalty −0.20 if missed"} for c in ir["constraints"]]
            rows.append({"what": f"limit {ir['output']['limit']}", "strictness": "—",
                         "effect": "number of results"})
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            st.caption("Summarised from the expected IR: what each condition will do.")
        else:
            st.error("Semantic analysis found an error, so the request stops here: "
                     + ", ".join(exp["diagnostics"]), icon="⛔")
    elif name == "IR":
        if exp.get("ir"):
            left, right = st.columns([3, 2])
            left.json(exp["ir"], expanded=2)
            right.markdown("**IR hash** (meaning fingerprint)")
            right.markdown(f'<span class="cv-hash">{exp["ir_hash_prefix"]}…</span>',
                           unsafe_allow_html=True)
            right.markdown("**Rules applied**")
            for r in exp.get("rules_fired", []):
                right.markdown(f"- `{r}`")
        else:
            st.info("No IR: compilation stopped on an ERROR.", icon="📦")
    elif name == "Plan":
        if exp["ok"]:
            prog = exp["program_optimized" if optimize else "program_unoptimized"]
            st.graphviz_chart(plan_dot(prog, optimize))
            st.caption("Optimizer on: the orange MASK is computed once and shared by every "
                       "search." if optimize else "Optimizer off: the canonical reference plan.")
        else:
            st.info("No plan after an ERROR.", icon="🗺️")
    elif name == "Program":
        if exp["ok"]:
            st.markdown(
                program_diff_html(exp["program_unoptimized"], exp["program_optimized"]),
                unsafe_allow_html=True,
            )
            st.caption("Red lines are removed and green lines added by the optimizer. "
                       "Results are identical either way (the equivalence test proves it).")
            prog = exp["program_optimized" if optimize else "program_unoptimized"]
            ops = [INSTR_RE.match(line).group(2) for line in prog if INSTR_RE.match(line)]
            st.dataframe(
                pd.DataFrame([{"instruction": line, "what it does": OPCODE_MEANING.get(op, "")}
                              for line, op in zip(prog, ops, strict=True)]),
                hide_index=True, width="stretch",
            )
        else:
            st.info("No program after an ERROR.", icon="⚙️")

with compare_tab:
    ids = list(examples)
    a_col, b_col = st.columns(2)
    a = a_col.selectbox("Request A", ids, index=ids.index("EX23"),
                        format_func=lambda k: f"{k} · {examples[k]['text']}")
    b = b_col.selectbox("Request B", ids, index=ids.index("EX24"),
                        format_func=lambda k: f"{k} · {examples[k]['text']}")
    ea, eb = examples[a]["expected"], examples[b]["expected"]
    if ea.get("ir") and eb.get("ir"):
        same = ea["ir_hash_prefix"] == eb["ir_hash_prefix"]
        (st.success if same else st.info)(
            f"IR hash A `{ea['ir_hash_prefix']}` vs B `{eb['ir_hash_prefix']}` — "
            + ("**same meaning**: different words, identical compiled request."
               if same else "different meanings."),
            icon="🟰" if same else "↔️",
        )
        strip = {"source", "diagnostics"}
        a_col.json({k: v for k, v in ea["ir"].items() if k not in strip}, expanded=1)
        b_col.json({k: v for k, v in eb["ir"].items() if k not in strip}, expanded=1)
    else:
        st.info("One of these requests stops with an error, so it has no IR to compare.")

st.caption(
    f"Dataset {manifest['dataset']['name']} · {manifest['catalog']['rows']:,} movies · "
    f"movies.csv sha256 {manifest['dataset']['files']['movies.csv']['sha256'][:12]}… · "
    "IR version 1.0 · preview"
)
