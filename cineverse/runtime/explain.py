"""Evidence-only explanations: fixed templates, at most four reasons per movie.

Spec: CineVerse_Recommendation_Engine_Specification §2 (11.6), §4. T01 C1 (signature), C10, C15.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cineverse.compiler.ir import CompiledQuery, Constraint
from cineverse.runtime.catalog import Catalog, MovieRecord
from cineverse.runtime.context import RankedList

MAX_REASONS = 4
BOUND_WORDS = {">=": "at least", ">": "above", "<=": "at most", "<": "below"}


@dataclass(frozen=True)
class Recommendation:
    movie_id: int
    title: str
    year: int | None
    genres: tuple[str, ...]
    score: float
    reasons: tuple[str, ...]
    evidence: dict[str, Any] = field(default_factory=dict)


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _fmt(v: Any) -> str:
    return f"{v:g}" if isinstance(v, float) else str(v)


def _year_bound(bounds: list[Constraint]) -> str:
    """'from Y' (>=), 'after Y' (>), 'until Y' (<=), 'before Y' (<), 'Y1–Y2' (T01 C10)."""
    lo = [c for c in bounds if c.op in (">=", ">")]
    hi = [c for c in bounds if c.op in ("<=", "<")]
    low = max(lo, key=lambda c: (c.value, c.op == ">")) if lo else None
    high = min(hi, key=lambda c: (c.value, c.op != "<")) if hi else None
    if low is not None and high is not None and low.op == ">=" and high.op == "<=":
        return f"{_fmt(low.value)}–{_fmt(high.value)}"
    words = []
    if low is not None:
        words.append(f"{'from' if low.op == '>=' else 'after'} {_fmt(low.value)}")
    if high is not None:
        words.append(f"{'until' if high.op == '<=' else 'before'} {_fmt(high.value)}")
    return ", ".join(words)


def _hard_reasons(rec: MovieRecord, hard: list[Constraint]) -> list[str]:
    out = []
    years = [c for c in hard if c.field == "year"]
    if years and rec.year is not None:
        out.append(f"Released {rec.year} ({_year_bound(years)})")
    for c in hard:
        if c.field == "rating" and rec.rating is not None:
            out.append(f"Rated {rec.rating:.1f}★ ({BOUND_WORDS[c.op]} {_fmt(c.value)})")
        elif c.field == "votes":
            word = BOUND_WORDS[c.op]
            out.append(f"{rec.votes} ratings ({word} {_fmt(c.value)})")
        elif c.field == "genre" and c.op == "NOT_HAS":
            out.append(f"Not {c.value}")
    return out


def _soft_violation(rec: MovieRecord, c: dict[str, Any]) -> str:
    if c["field"] == "year":
        if rec.year is None:
            return "Release year unknown, so your preferred years could not be checked"
        side = "earlier" if c["op"] in (">=", ">") else "later"
        return f"Released {rec.year}, {side} than you preferred"
    return f"Does not meet your preference {c['field']} {c['op']} {_fmt(c['value'])}"


def reasons_for(rec: MovieRecord, ev: dict[str, Any], ir: CompiledQuery | None) -> list[str]:
    """Reasons in template order (Engine Spec §4), each only when its evidence exists."""
    soft = ev.get("soft", {})
    out: list[str] = []

    genres = list(ev.get("matched_genres", []))
    genres += [v for kind, v, _ in soft.get("pos_matches", []) if kind == "genre"]
    genres = [g for g in dict.fromkeys(genres) if g in rec.genres]
    if genres:
        out.append(f"Genres {_join(genres)} match your request")

    tag_pairs = [tuple(p) for p in ev.get("matched_tags", [])]
    tag_pairs += [(v, hit) for kind, v, hit in soft.get("pos_matches", []) if kind == "text"]
    for term, tag in dict.fromkeys(tag_pairs):
        out.append(f"Tagged '{tag}', matching '{term}'")

    if "semantic_rank" in ev and ir is not None and ir.semantic_text:
        out.append(f"Close in meaning to '{ir.semantic_text}' (rank {ev['semantic_rank']})")
    if "metadata_rank" in ev:
        out.append(f"Matches your genres and keywords (rank {ev['metadata_rank']})")
    if "popularity_rank" in ev and ev.get("rating") is not None:
        out.append(f"Highly rated: {ev['rating']:.1f}★ from {ev['votes']} ratings")

    if ir is not None:
        out += _hard_reasons(rec, [c for c in ir.constraints if c.strictness == "hard"])

    for kind, value, hit in soft.get("neg_matches", []):
        what = value if kind == "genre" else f"'{hit}'"
        out.append(f"Includes {what}, which you wanted little of")
    for c in soft.get("violated", []):
        out.append(_soft_violation(rec, c))
    return out


def explain(catalog: Catalog, rl: RankedList, ir: CompiledQuery | None) -> list[Recommendation]:
    """EXPLAIN: one Recommendation per ranked movie; the trace keeps all evidence."""
    out = []
    for mid, score in zip(rl.ids, rl.scores, strict=True):
        rec = catalog.get(mid)
        ev = rl.evidence.get(mid, {})
        out.append(
            Recommendation(
                movie_id=rec.movie_id,
                title=rec.title,
                year=rec.year,
                genres=rec.genres,
                score=score,
                reasons=tuple(reasons_for(rec, ev, ir)[:MAX_REASONS]),
                evidence=ev,
            )
        )
    return out
