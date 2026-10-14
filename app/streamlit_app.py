"""CineVerse Streamlit app: describe a movie, get explained results, inspect every compiler stage.

Calls only the public API (`cineverse.recommend`, `cineverse.status`) and renders the
CompilationResult / ExecutionResult it returns (LR-4, LA-01, LA-02: no scoring in the UI).
Run: streamlit run app/streamlit_app.py
Spec: CineVerse_UI_UX_and_API_Specification §1, §2, §5, §6.
"""

from __future__ import annotations

import html
import json
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cineverse

EXAMPLES = [
    "thoughtful sci-fi mystery after 2010, little romance, top 5",
    "no romance",
    "only comedies in the 90s",
    "comedy under 2 hours",
    "only horror and no horror",
    "ideally no horror, mystery",
]
SEVERITY = {"ERROR": ("⛔", "Error", st.error), "WARNING": ("⚠️", "Warning", st.warning),
            "INFO": ("ℹ️", "Info", st.info)}
TOKEN_COLOURS = {
    "GENRE": "#4ade80", "DESCRIPTOR": "#60a5fa", "WORD": "#d6a77a", "NEG_HARD": "#f87171",
    "NEG_SOFT": "#fb923c", "HEDGE": "#fbbf24", "STRICT": "#c084fc", "CMP": "#22d3ee",
    "NUMBER": "#22d3ee", "DECADE": "#22d3ee", "UNIT": "#22d3ee", "FIELD": "#22d3ee",
    "BETWEEN": "#22d3ee", "TO": "#22d3ee", "LIMIT": "#94a3b8", "ITEM": "#94a3b8",
    "DIVERSE": "#94a3b8", "SEP": "#64748b", "OR": "#64748b", "FILLER": "#475569",
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
STAGES = ["lex", "parse", "analyse", "lower", "passes", "plan", "optimize", "codegen"]

CSS = """
<style>
.block-container {padding-top: 1.4rem; max-width: 1250px;}
.cv-hero {background: radial-gradient(circle at 15% 20%, #7c3aed55 0, transparent 45%),
  radial-gradient(circle at 85% 30%, #06b6d455 0, transparent 40%),
  linear-gradient(135deg, #0b0b14 0%, #1a1033 55%, #0b2235 100%);
  border: 1px solid #2b2b40; border-radius: 22px; padding: 26px 32px 22px; margin-bottom: 12px;}
.cv-hero h1 {font-size: 2.5rem; margin: 0; letter-spacing: -0.02em;
  background: linear-gradient(90deg, #f5f3ff, #c4b5fd 45%, #67e8f9);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;}
.cv-hero p {color: #cbd5e1; margin: 6px 0 0; font-size: 1.02rem;}
.cv-tokens {font-size: 1.3rem; line-height: 3rem; padding: 8px 14px; background:#11111a;
  border:1px solid #26263a; border-radius: 14px;}
.cv-tok {position: relative; padding: 2px 3px; border-bottom: 3px solid; border-radius: 3px;}
.cv-tok sub {position:absolute; left:0; top:1.85rem; font-size:.55rem; white-space:nowrap;}
.cv-src mark {background:#f59e0b55; color:inherit; border-radius:3px; padding:0 2px;}
.cv-card {border-radius:16px; overflow:hidden; background:#12121c; border:1px solid #26263a;
  transition: transform .15s ease, border-color .15s ease;}
.cv-card:hover {transform: translateY(-3px); border-color:#7c3aed;}
.cv-poster {height:130px; position:relative; padding:12px 14px; display:flex;
  flex-direction:column; justify-content:space-between;}
.cv-rank {align-self:flex-start; background:#000a; color:#fff; border-radius:10px;
  padding:2px 9px; font-weight:700; font-size:.85rem;}
.cv-score {position:absolute; right:12px; bottom:10px; background:#000a; color:#fde68a;
  border-radius:10px; padding:2px 8px; font-size:.78rem; font-weight:700;}
.cv-emoji {position:absolute; right:12px; top:8px; font-size:2.4rem;}
.cv-title {color:#fff; font-weight:800; font-size:1.05rem; line-height:1.25;
  text-shadow:0 2px 8px #000c; max-width: 80%;}
.cv-body {padding:10px 14px 12px;}
.cv-meta {color:#94a3b8; font-size:.8rem; margin-bottom:6px;}
.cv-chip {display:inline-block; padding:1px 8px; border-radius:999px; font-size:.7rem;
  margin:0 3px 3px 0; background:#23233a; color:#cbd5e1;}
.cv-reason {color:#e2e8f0; font-size:.8rem; margin:3px 0;}
.cv-ok {display:inline-block; padding:3px 10px; border-radius:999px; font-size:.8rem;
  background:#14532d; color:#bbf7d0; border:1px solid #16a34a;}
.cv-diff-del {background:#7f1d1d55; color:#fecaca; text-decoration: line-through;}
.cv-diff-add {background:#14532d66; color:#bbf7d0;}
.cv-code {font-family: ui-monospace, Consolas, monospace; font-size:.8rem; white-space:pre;
  background:#0d0d14; border:1px solid #26263a; border-radius:12px; padding:10px 12px;
  overflow-x:auto;}
</style>
"""


# --------------------------------------------------------------------------- data


@st.cache_resource(show_spinner="Loading catalogue, embedding model and index (first time only)…")
def get_status() -> dict[str, Any]:
    return cineverse.status()


def run_request(text: str) -> dict[str, Any]:
    """Run the request with the optimizer off and on (cached in the session per text)."""
    cache = st.session_state.setdefault("runs", {})
    if text not in cache:
        out = {}
        for optimize in (False, True):
            t0 = time.perf_counter()
            comp, exe = cineverse.recommend(text, optimize=optimize)
            out[optimize] = {"comp": comp, "exe": exe, "ms": (time.perf_counter() - t0) * 1000}
        cache[text] = out
    return cache[text]


# --------------------------------------------------------------------------- rendering helpers


def highlight(text: str, spans: list[tuple[int, int]]) -> str:
    out, pos = [], 0
    for s, e in sorted(spans):
        if s < pos:
            continue
        out += [html.escape(text[pos:s]), f"<mark>{html.escape(text[s:e])}</mark>"]
        pos = e
    out.append(html.escape(text[pos:]))
    return f'<span class="cv-src">{"".join(out)}</span>'


def token_html(text: str, tokens: list[Any]) -> str:
    out, pos = [], 0
    for t in sorted((t for t in tokens if t.type.value != "FILLER"), key=lambda t: t.span[0]):
        s, e = t.span
        colour = TOKEN_COLOURS.get(t.type.value, "#94a3b8")
        value = ",".join(t.value) if isinstance(t.value, tuple) else t.value
        tip = html.escape(f"{t.type.value} → {value}")
        out += [html.escape(text[pos:s]),
                f'<span class="cv-tok" style="border-color:{colour}" title="{tip}">'
                f'{html.escape(text[s:e])}<sub style="color:{colour}">{t.type.value}</sub></span>']
        pos = e
    out.append(html.escape(text[pos:]))
    return f'<div class="cv-tokens">{"".join(out)}</div>'


def show_diagnostics(text: str, diagnostics: list[Any]) -> None:
    """Never hide a warning (UX principle 2); icon + word + colour (§5)."""
    for d in diagnostics:
        icon, word, show = SEVERITY[d.severity.value]
        body = f"**{word} {d.code}** — {d.message}"
        if d.hint:
            body += f"  \n_Hint: {d.hint}_"
        if d.span is not None:
            body += f"  \n{highlight(text, [d.span])}"
        show(body, icon=icon)


def stars(rating: float | None) -> str:
    if rating is None:
        return "unrated"
    full = round(rating)
    return "★" * full + "☆" * (5 - full) + f" {rating:.1f}"


def card_html(rank: int, rec: Any) -> str:
    genres = list(rec.genres)
    colours = [GENRE_STYLE.get(g, ("🎬", "#475569"))[1] for g in genres[:2]] or ["#475569"]
    if len(colours) == 1:
        colours.append("#0b0b14")
    emoji = GENRE_STYLE.get(genres[0], ("🎬", ""))[0] if genres else "🎬"
    rating = rec.evidence.get("rating")
    chips = "".join(f'<span class="cv-chip">{html.escape(g)}</span>' for g in genres[:4])
    reasons = "".join(f'<div class="cv-reason">• {html.escape(r)}</div>' for r in rec.reasons)
    year = rec.year if rec.year is not None else "—"
    meta = f"{year}" + (f" · {stars(rating)}" if rating is not None else "")
    return (
        f'<div class="cv-card"><div class="cv-poster" style="background:linear-gradient(135deg,'
        f'{colours[0]} 0%, {colours[1]} 100%)"><span class="cv-rank">#{rank}</span>'
        f'<span class="cv-emoji">{emoji}</span><span class="cv-score">{rec.score:.2f}</span>'
        f'<div class="cv-title">{html.escape(rec.title)}</div></div>'
        f'<div class="cv-body"><div class="cv-meta">{meta}</div>{chips}{reasons}</div></div>'
    )


@st.dialog("Why this movie?", width="large")
def why_dialog(rec: Any, text: str) -> None:
    st.markdown(f"### {rec.title} ({rec.year if rec.year is not None else '—'})")
    st.caption(f"for “{text}” · score {rec.score:.4f}")
    ev = rec.evidence
    soft = ev.get("soft", {})
    left, right = st.columns(2)
    with left:
        st.markdown("**How it was found**")
        for key, label in (("semantic_rank", "Semantic search rank"),
                           ("metadata_rank", "Genre/tag match rank"),
                           ("popularity_rank", "Popularity rank")):
            if key in ev:
                st.markdown(f"- {label}: **{ev[key]}**")
        if "rrf" in ev:
            st.markdown(f"- Fused (RRF / Z): **{ev['rrf']:.4f}**")
        st.markdown("**Soft scoring**")
        for kind, value, hit in soft.get("pos_matches", []):
            st.markdown(f"- 💚 +0.10 {kind} *{value}* (matched {hit})")
        for kind, value, hit in soft.get("neg_matches", []):
            st.markdown(f"- 🔻 −0.30 {kind} *{value}* (matched {hit})")
        for c in soft.get("violated", []):
            st.markdown(f"- 🔻 −0.20 missed {c['field']} {c['op']} {c['value']}")
        if not any(soft.get(k) for k in ("pos_matches", "neg_matches", "violated")):
            st.markdown("- no soft adjustments")
    with right:
        st.markdown("**Reasons shown**")
        for r in rec.reasons or ["—"]:
            st.markdown(f"- {r}")
        st.markdown("**Full evidence (from the trace)**")
        st.json(ev, expanded=1)


def plan_dot(plan: Any, highlight_ops: set[str]) -> str:
    lines = ['digraph plan {', 'rankdir=LR; bgcolor="transparent";',
             'node [shape=box, style="rounded,filled", fillcolor="#1e1b3a", color="#7c3aed", '
             'fontcolor="#f1f5f9", fontname="Helvetica"];', 'edge [color="#94a3b8"];']
    for n in plan.nodes.values():
        fill = "#9a3412" if n.op in highlight_ops else "#1e1b3a"
        c = n.args.get("c")
        extra = f"\\nc={c}" if c is not None else ""
        lines.append(f'"{n.id}" [label="{n.id}\\n{n.op}{extra}", fillcolor="{fill}"];')
        for i in n.inputs:
            lines.append(f'"{i}" -> "{n.id}";')
    lines.append("}")
    return "\n".join(lines)


def program_diff(before: list[str], after: list[str]) -> str:
    import difflib

    rows = []
    for line in difflib.ndiff(before, after):
        tag, body = line[:1], html.escape(line[2:])
        if tag == "-":
            rows.append(f'<div class="cv-diff-del">− {body}</div>')
        elif tag == "+":
            rows.append(f'<div class="cv-diff-add">+ {body}</div>')
        elif tag == " ":
            rows.append(f"<div>&nbsp; {body}</div>")
    return f'<div class="cv-code">{"".join(rows)}</div>'


def ast_tree(node: Any, depth: int = 0) -> list[str]:
    if not isinstance(node, dict):
        return []
    fields = {k: v for k, v in node.items() if k not in ("kind", "node_id", "span", "source")
              and not isinstance(v, (list, dict))}
    label = f"{node['kind']}({', '.join(f'{k}={v!r}' for k, v in fields.items())})"
    span = node.get("span")
    lines = [f"{'│  ' * depth}{label}  {span}"]
    for value in node.values():
        if isinstance(value, list):
            for child in value:
                lines += ast_tree(child, depth + 1)
    return lines


# --------------------------------------------------------------------------- page

st.set_page_config(page_title="CineVerse", page_icon="🎬", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
st.markdown(
    '<div class="cv-hero"><h1>🎬 CineVerse</h1><p>Describe the movie you want in plain '
    "English. A compiler turns your words into a checked, optimized plan — and every result "
    "says why.</p></div>",
    unsafe_allow_html=True,
)

try:
    info = get_status()
except Exception as exc:
    st.error(f"CineVerse could not start: {exc}")
    st.code("python -m cineverse.data.prepare\npython -m cineverse.data.build_index",
            language="bash")
    st.stop()

if "request" not in st.session_state:
    st.session_state.request = EXAMPLES[0]


def use_example(text: str) -> None:
    st.session_state.request = text


with st.form("ask", border=False):
    col_in, col_go = st.columns([6, 1], vertical_alignment="bottom")
    col_in.text_input("Describe a movie", key="request", max_chars=300,
                      placeholder="thoughtful sci-fi mystery after 2010, little romance, top 5")
    col_go.form_submit_button("Go", type="primary", width="stretch")

st.caption("Try:")
cols = st.columns(len(EXAMPLES))
for col, ex in zip(cols, EXAMPLES, strict=True):
    col.button(ex, key=f"ex_{ex}", on_click=use_example, args=(ex,), width="stretch")

opt_col, info_col = st.columns([1, 3])
optimize = opt_col.toggle("⚡ Optimizer on", value=True)
info_col.caption(
    f"catalogue: ml-latest-small · {info['catalog_rows']:,} movies · semantic search "
    f"{'on' if info['semantic'] else 'OFF (metadata only)'}"
)

text = st.session_state.request.strip()
if not text:
    st.info("Type a request above, for example “no romance” or “dark thriller after 2000”.")
    st.stop()

runs = run_request(st.session_state.request)
chosen = runs[optimize]
comp, exe = chosen["comp"], chosen["exe"]
other = runs[not optimize]

st.markdown(token_html(comp.source, comp.tokens), unsafe_allow_html=True)
show_diagnostics(comp.source, comp.diagnostics + (exe.diagnostics if exe else []))

results_tab, compiler_tab = st.tabs(["🎬 Results", "🛠️ Compiler view"])

with results_tab:
    if not comp.ok:
        st.error("Compilation stopped before planning, so nothing was searched. "
                 "Fix the highlighted condition and try again.", icon="⛔")
    elif exe is None or not exe.ok:
        st.error(f"Execution failed: {exe.error if exe else 'unknown'}", icon="⛔")
    elif not exe.results:
        hard = [f"{c.field} {c.op} {c.value}" for c in comp.ir.constraints
                if c.strictness == "hard"]
        st.info("No movie satisfies all strict conditions: " + ", ".join(hard), icon="ℹ️")
    else:
        same = [(r.movie_id, round(r.score, 6)) for r in exe.results] == \
               [(r.movie_id, round(r.score, 6)) for r in (other["exe"].results if other["exe"]
                                                          else [])]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Results", len(exe.results))
        m2.metric("Rules applied", len(comp.rule_log),
                  help="\n".join(r.display() for r in comp.rule_log) or "none")
        m3.metric("Execution", f"{exe.ms:.0f} ms",
                  delta=f"{exe.ms - other['exe'].ms:+.0f} ms vs optimizer "
                        f"{'off' if optimize else 'on'}", delta_color="inverse")
        badge = "✓ optimizer on/off give identical results" if same else "✗ results differ"
        m4.markdown(f'<span class="cv-ok">{badge}</span>', unsafe_allow_html=True)
        per_row = 3 if len(exe.results) <= 12 else 4
        for start in range(0, len(exe.results), per_row):
            row = st.columns(per_row)
            for col, (rank, rec) in zip(row, enumerate(exe.results[start:start + per_row],
                                                       start + 1), strict=False):
                with col:
                    st.markdown(card_html(rank, rec), unsafe_allow_html=True)
                    if st.button("Why this movie?", key=f"why_{rank}", width="stretch"):
                        why_dialog(rec, comp.source)

with compiler_tab:
    tabs = st.tabs(["Tokens", "AST", "Semantic", "IR", "Plan", "Program", "Timings", "Trace"])
    parts = comp.to_trace_parts()
    with tabs[0]:
        st.dataframe(pd.DataFrame(
            [{"type": t["type"], "lexeme": t["lexeme"],
              "value": ", ".join(t["value"]) if isinstance(t["value"], list)
              else "" if t["value"] is None else str(t["value"]),
              "span": f"[{t['span'][0]}, {t['span'][1]})"} for t in parts["tokens"]]),
            hide_index=True, width="stretch")
        st.caption("FILLER words are kept here for the trace and removed before parsing.")
    with tabs[1]:
        if parts["ast"]:
            st.code("\n".join(ast_tree(parts["ast"])), language=None)
            if st.toggle("Show AST as JSON"):
                st.json(parts["ast"], expanded=2)
    with tabs[2]:
        if comp.semantic is not None:
            rows = [{"node": node_id, "kind": a.kind, "field": a.field, "op": a.op,
                     "value": str(a.value), "strictness": a.strictness,
                     "polarity": "" if a.polarity is None else str(a.polarity),
                     "applied": a.applied}
                    for node_id, anns in comp.semantic.annotations.items() for a in anns]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    with tabs[3]:
        if comp.ir is not None:
            left, right = st.columns(2)
            left.markdown("**Lowered IR**")
            left.json(parts["ir_lowered"], expanded=2)
            right.markdown("**After passes (O2, O1)**")
            right.json(parts["ir"], expanded=2)
            st.markdown(f"**IR hash** `{comp.ir.hash()[:16]}…`")
            for r in comp.rule_log:
                if r.level == "ir":
                    st.markdown(f"- `{r.display()}`")
        else:
            st.info("No IR: compilation stopped on an ERROR.")
    with tabs[4]:
        if comp.plan is not None:
            left, right = st.columns(2)
            left.markdown("**Canonical plan (unoptimized)**")
            left.graphviz_chart(plan_dot(comp.plan_unoptimized, set()))
            right.markdown("**Optimized plan** (shared MASK in orange)" if optimize
                           else "**Optimizer off**")
            right.graphviz_chart(plan_dot(comp.plan, {"Mask"}))
            for r in comp.rule_log:
                if r.level == "plan":
                    st.markdown(f"- `{r.display()}`")
    with tabs[5]:
        if comp.program:
            plain = runs[False]["comp"].printed_program()
            opt = runs[True]["comp"].printed_program()
            st.markdown(program_diff(plain, opt), unsafe_allow_html=True)
            st.caption("Red: removed by the optimizer · green: added. Results are identical.")
    with tabs[6]:
        stage_rows = [{"stage": s, "optimizer off": runs[False]["comp"].timings_ms.get(s, 0.0),
                       "optimizer on": runs[True]["comp"].timings_ms.get(s, 0.0)} for s in STAGES]
        st.markdown("**Compiler stages (ms)**")
        st.bar_chart(pd.DataFrame(stage_rows).set_index("stage"), stack=False)
        if exe is not None and runs[False]["exe"] is not None:
            def per_op(e: Any) -> dict[str, float]:
                agg: dict[str, float] = {}
                for r in e.execution:
                    agg[r["opcode"]] = agg.get(r["opcode"], 0.0) + r["ms"]
                return agg
            a, b = per_op(runs[False]["exe"]), per_op(runs[True]["exe"])
            ops = sorted(set(a) | set(b), key=lambda o: -max(a.get(o, 0), b.get(o, 0)))
            st.markdown("**Instructions (ms, summed per opcode)**")
            st.bar_chart(pd.DataFrame([{"opcode": o, "optimizer off": a.get(o, 0.0),
                                        "optimizer on": b.get(o, 0.0)} for o in ops])
                         .set_index("opcode"), stack=False)
            st.dataframe(pd.DataFrame(exe.execution), hide_index=True, width="stretch")
    with tabs[7]:
        if exe is not None:
            st.json(exe.trace, expanded=1)
            st.download_button("Download trace JSON", json.dumps(exe.trace, indent=2),
                               file_name=f"cineverse_trace_{exe.trace['request_id']}.json",
                               mime="application/json")
        else:
            st.json(parts, expanded=1)

st.caption(
    f"dataset {info['dataset_sha256']} · model {info['model']} · IR {info['ir']} · "
    f"registry {info['registry']} · build {info['commit']}"
)
