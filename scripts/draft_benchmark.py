"""Draft the 95 remaining benchmark requests (human task H1) for team review.

Each request carries a hand-written expectation derived from the specification, written
independently of the compiler. The compiler's output is recorded as a *proposed* gold IR and
compared with the expectation; every disagreement is flagged. Nothing here is final until the
team reviews it (Evaluation Plan §2: gold IR written from the spec, reviewed by a second member).

Writes benchmark/drafts/requests_draft.jsonl and benchmark/drafts/REVIEW.md.
"""

from __future__ import annotations

import json
from pathlib import Path

from cineverse import default_runtime
from cineverse.compiler.driver import compile_text
from cineverse.compiler.ir import format_constraint

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "benchmark" / "drafts"

# (category, text, expectation, expected diagnostic codes)
# expectation tokens: "pref genre:X+" / "pref text:t-", "hard year >= 2011", "soft ...", "limit N"
VALID: list[tuple[str, str, list[str], list[str]]] = [
    ("single_genre", "westerns", ["pref genre:Western+"], []),
    ("single_genre", "documentaries", ["pref genre:Documentary+"], []),
    ("single_genre", "something scary", ["pref genre:Horror+"], []),
    ("single_genre", "film noir", ["pref genre:Film-Noir+"], []),
    ("single_genre", "i want to watch a musical", ["pref genre:Musical+"], ["P001"]),
    ("single_genre", "fantasy movies", ["pref genre:Fantasy+"], []),
    ("single_genre", "war films", ["pref genre:War+"], []),
    ("single_genre", "animation", ["pref genre:Animation+"], []),
    ("multi_genre", "crime thriller", ["pref genre:Crime+", "pref genre:Thriller+"], []),
    ("multi_genre", "sci-fi horror", ["pref genre:Sci-Fi+", "pref genre:Horror+"], []),
    ("multi_genre", "romantic comedy", ["pref genre:Romance+", "pref genre:Comedy+"], []),
    ("multi_genre", "animated family movies", ["pref genre:Animation+", "pref genre:Children+"],
     []),
    ("multi_genre", "action adventure", ["pref genre:Action+", "pref genre:Adventure+"], []),
    ("multi_genre", "mystery thriller with crime",
     ["pref genre:Mystery+", "pref genre:Thriller+", "pref genre:Crime+"], []),
    ("multi_genre", "war drama", ["pref genre:War+", "pref genre:Drama+"], []),
    ("multi_genre", "comedy or drama", ["pref genre:Comedy+", "pref genre:Drama+"], []),
    ("descriptor_only", "something thought-provoking", ["pref text:thought-provoking+"], []),
    ("descriptor_only", "feel-good", ["pref text:feel-good+"], []),
    ("descriptor_only", "time travel", ["pref text:time travel+"], []),
    ("descriptor_only", "dark and atmospheric", ["pref text:dark+", "pref text:atmospheric+"], []),
    ("descriptor_only", "heist", ["pref text:heist+"], []),
    ("descriptor_only", "mind-bending twist ending",
     ["pref text:mind-bending+", "pref text:twist ending+"], []),
    ("descriptor_only", "zombies", ["pref text:zombies+"], []),
    ("descriptor_only", "a quiet slow burn", ["pref text:quiet+", "pref text:slow burn+"], []),
    ("hard_exclusion", "comedy, no romance",
     ["pref genre:Comedy+", "hard genre NOT_HAS Romance"], []),
    ("hard_exclusion", "action without war", ["pref genre:Action+", "hard genre NOT_HAS War"], []),
    ("hard_exclusion", "no horror or thriller",
     ["hard genre NOT_HAS Horror", "hard genre NOT_HAS Thriller"], []),
    ("hard_exclusion", "drama but not romance",
     ["pref genre:Drama+", "hard genre NOT_HAS Romance"], []),
    ("hard_exclusion", "avoid animation, sci-fi",
     ["hard genre NOT_HAS Animation", "pref genre:Sci-Fi+"], []),
    ("hard_exclusion", "exclude musicals, family movie",
     ["hard genre NOT_HAS Musical", "pref genre:Children+"], []),
    ("hard_exclusion", "thriller, never horror",
     ["pref genre:Thriller+", "hard genre NOT_HAS Horror"], []),
    ("hard_exclusion", "mystery excluding crime",
     ["pref genre:Mystery+", "hard genre NOT_HAS Crime"], []),
    ("soft_exclusion", "comedy, little romance", ["pref genre:Comedy+", "pref genre:Romance-"], []),
    ("soft_exclusion", "action, not too violent", ["pref genre:Action+", "pref text:violent-"], []),
    ("soft_exclusion", "drama with less romance", ["pref genre:Drama+", "pref genre:Romance-"],
     []),
    ("soft_exclusion", "sci-fi, light on action", ["pref genre:Sci-Fi+", "pref genre:Action-"],
     []),
    ("soft_exclusion", "thriller, barely any gore", ["pref genre:Thriller+", "pref text:gore-"],
     []),
    ("soft_exclusion", "fantasy, not much romance",
     ["pref genre:Fantasy+", "pref genre:Romance-"], []),
    ("soft_exclusion", "adventure, minimal violence",
     ["pref genre:Adventure+", "pref text:violence-"], []),
    ("soft_exclusion", "crime drama, low on comedy",
     ["pref genre:Crime+", "pref genre:Drama+", "pref genre:Comedy-"], []),
    ("year", "comedies from the 80s",
     ["pref genre:Comedy+", "hard year >= 1980", "hard year <= 1989"], ["P001"]),
    ("year", "drama released before 1980", ["pref genre:Drama+", "hard year <= 1979"], []),
    ("year", "horror after 2005", ["pref genre:Horror+", "hard year >= 2006"], []),
    ("year", "westerns between 1960 and 1975",
     ["pref genre:Western+", "hard year >= 1960", "hard year <= 1975"], []),
    ("year", "1990s thrillers",
     ["pref genre:Thriller+", "hard year >= 1990", "hard year <= 1999"], []),
    ("year", "sci-fi since 2015", ["pref genre:Sci-Fi+", "hard year >= 2015"], []),
    ("year", "animation up to 2000", ["pref genre:Animation+", "hard year <= 2000"], []),
    ("year", "musicals made before 1970", ["pref genre:Musical+", "hard year <= 1969"], []),
    ("rating_votes", "comedy rated at least 4", ["pref genre:Comedy+", "hard rating >= 4.0"], []),
    ("rating_votes", "dramas rated above 3.5 stars", ["pref genre:Drama+", "hard rating > 3.5"],
     []),
    ("rating_votes", "thrillers with at least 200 ratings",
     ["pref genre:Thriller+", "hard votes >= 200"], []),
    ("rating_votes", "sci-fi rated at least 4 with more than 50 votes",
     ["pref genre:Sci-Fi+", "hard rating >= 4.0", "hard votes >= 51"], []),
    ("rating_votes", "horror rated below 3", ["pref genre:Horror+", "hard rating < 3.0"], []),
    ("rating_votes", "animated movies rated at least 4.5",
     ["pref genre:Animation+", "hard rating >= 4.5"], []),
    ("rating_votes", "documentaries with at most 20 ratings",
     ["pref genre:Documentary+", "hard votes <= 20"], []),
    ("rating_votes", "action rated at least 3 stars, at least 100 votes",
     ["pref genre:Action+", "hard rating >= 3.0", "hard votes >= 100"], []),
    ("hedged", "preferably after 2010, comedy", ["soft year >= 2011", "pref genre:Comedy+"], []),
    ("hedged", "ideally rated at least 4, drama", ["soft rating >= 4.0", "pref genre:Drama+"], []),
    ("hedged", "maybe a thriller", ["pref genre:Thriller+"], []),
    ("hedged", "preferably no horror, mystery", ["pref genre:Horror-", "pref genre:Mystery+"], []),
    ("hedged", "if possible before 2000, western", ["soft year <= 1999", "pref genre:Western+"],
     []),
    ("hedged", "comedy, preferably at least 100 ratings",
     ["pref genre:Comedy+", "soft votes >= 100"], []),
    ("hedged", "rather a romance", ["pref genre:Romance+"], []),
    ("hedged", "ideally released after 2000, sci-fi", ["soft year >= 2001", "pref genre:Sci-Fi+"],
     []),
    ("limit", "top 3 comedies", ["limit 3", "pref genre:Comedy+"], []),
    ("limit", "show me 7 thrillers", ["limit 7", "pref genre:Thriller+"], []),
    ("limit", "give me 12 dramas", ["limit 12", "pref genre:Drama+"], []),
    ("limit", "list 20 horror movies", ["limit 20", "pref genre:Horror+"], []),
    ("limit", "recommend five westerns", ["limit 5", "pref genre:Western+"], []),
    ("limit", "top 1 sci-fi", ["limit 1", "pref genre:Sci-Fi+"], []),
    ("limit", "suggest 4 heist movies", ["limit 4", "pref text:heist+"], []),
    ("limit", "two romantic comedies", ["pref genre:Romance+", "pref genre:Comedy+"], ["P002"]),
    ("combined", "dark sci-fi thriller after 2000, no horror, top 5",
     ["pref text:dark+", "pref genre:Sci-Fi+", "pref genre:Thriller+", "hard year >= 2001",
      "hard genre NOT_HAS Horror", "limit 5"], []),
    ("combined", "funny animated movies in the 90s rated at least 3.5",
     ["pref genre:Comedy+", "pref genre:Animation+", "hard year >= 1990", "hard year <= 1999",
      "hard rating >= 3.5"], []),
    ("combined", "crime drama between 1970 and 1995, little romance, show me 8",
     ["pref genre:Crime+", "pref genre:Drama+", "hard year >= 1970", "hard year <= 1995",
      "pref genre:Romance-", "limit 8"], []),
    ("combined", "feel-good family comedy, no horror, top 6",
     ["pref text:feel-good+", "pref genre:Children+", "pref genre:Comedy+",
      "hard genre NOT_HAS Horror", "limit 6"], []),
    ("combined", "thoughtful drama rated at least 4 with at least 100 ratings",
     ["pref text:thoughtful+", "pref genre:Drama+", "hard rating >= 4.0", "hard votes >= 100"],
     []),
    ("combined", "only westerns before 1980, top 4",
     ["hard genre HAS Western", "hard year <= 1979", "limit 4"], []),
    ("combined", "time travel sci-fi, preferably after 2000, no romance",
     ["pref text:time travel+", "pref genre:Sci-Fi+", "soft year >= 2001",
      "hard genre NOT_HAS Romance"], []),
]
INVALID: list[tuple[str, str, list[str]]] = [
    ("invalid", "only comedies, no comedy", ["S107"]),
    ("invalid", "only sci-fi and without sci-fi", ["S107"]),
    ("invalid", "must be horror, never horror", ["S107"]),
    ("invalid", "only animated films excluding animation", ["S107"]),
    ("invalid", "before 1990 and after 2000", ["S108"]),
    ("invalid", "rated at least 4.5 and rated below 3", ["S108"]),
    ("invalid", "between 2010 and 2000", ["S108"]),
    ("invalid", "drama under 90 minutes", ["S105"]),
    ("invalid", "thriller over 2 hours", ["S112", "S105"]),
    ("invalid", "diverse horror movies", ["S105"]),
    ("invalid", "comedy above 7", ["S102"]),
    ("invalid", "drama under 50", ["S102"]),
    ("invalid", "rated above 6", ["S104"]),
    ("invalid", "please", ["S111"]),
    ("invalid", "the a an", ["S111"]),
    ("invalid", "?!", ["L001", "L001", "S111"]),
]
EXTRA_DEV = {"single_genre", "multi_genre", "descriptor_only", "hard_exclusion"}  # 3 dev, else 2
INVALID_DEV = 6


def describe(comp) -> list[str]:
    """The compiled IR in the expectation notation."""
    ir = comp.ir
    out = [f"pref {p.kind}:{p.value}{'+' if p.polarity == 1 else '-'}" for p in ir.preferences]
    out += [f"{c.strictness} {format_constraint(c)}" for c in ir.constraints]
    if ir.output.limit != 10:
        out.append(f"limit {ir.output.limit}")
    return out


def baseline_spec(ir: dict) -> dict:
    from scripts.examples_to_benchmark import baseline_spec as make

    return make(ir)


def main() -> int:
    _, registry = default_runtime()
    from cineverse.config import load_runtime_config

    cfg = load_runtime_config()
    rows, flags = [], []
    dev_left: dict[str, int] = {}
    number = 26
    for category, text, expect, diags in VALID:
        quota = 3 if category in EXTRA_DEV else 2
        used = dev_left.setdefault(category, 0)
        split = "dev" if used < quota else "test"
        dev_left[category] = used + 1
        comp = compile_text(text, registry, cfg)
        got_diags = [d.code for d in comp.diagnostics]
        proposed = None
        got: list[str] = []
        if comp.ok and comp.ir is not None:
            data = json.loads(comp.ir.to_json())
            for key in ("source", "diagnostics"):
                data.pop(key)
            for c in data["constraints"]:
                c.pop("span")
            proposed = data
            got = describe(comp)
        item_flags = []
        if sorted(got) != sorted(expect):
            item_flags.append(f"IR differs: expected {sorted(expect)}, compiler {sorted(got)}")
        if got_diags != diags:
            item_flags.append(f"diagnostics differ: expected {diags}, compiler {got_diags}")
        rid = f"R{number:03d}"
        number += 1
        rows.append({"id": rid, "split": split, "category": category, "text": text,
                     "gold_ir": proposed, "gold_diagnostics": diags,
                     "baseline_spec": baseline_spec(proposed) if proposed else None,
                     "review": {"status": "draft", "expectation": expect,
                                "gold_ir_source": "compiler-proposed; check against expectation",
                                "flags": item_flags}})
        if item_flags:
            flags.append((rid, text, item_flags))
    for i, (category, text, diags) in enumerate(INVALID):
        comp = compile_text(text, registry, cfg)
        got_diags = [d.code for d in comp.diagnostics]
        item_flags = [] if got_diags == diags else [
            f"diagnostics differ: expected {diags}, compiler {got_diags}"]
        rid = f"R{number:03d}"
        number += 1
        rows.append({"id": rid, "split": "dev" if i < INVALID_DEV else "test",
                     "category": category, "text": text, "gold_ir": None,
                     "gold_diagnostics": diags, "baseline_spec": None,
                     "review": {"status": "draft", "flags": item_flags}})
        if item_flags:
            flags.append((rid, text, item_flags))

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "requests_draft.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    by_cat: dict[str, list[int]] = {}
    for r in rows:
        stats = by_cat.setdefault(r["category"], [0, 0])
        stats[0 if r["split"] == "dev" else 1] += 1
    lines = [
        "# H1 benchmark draft — review sheet", "",
        f"{len(rows)} drafted requests (R026–R{number - 1:03d}). **Status: draft — not used by "
        "any test or evaluation until approved and merged into `benchmark/requests.jsonl`.**", "",
        "Each request has a hand-written expectation from the specification, written "
        "independently of the compiler. `gold_ir` is the compiler's *proposal*; a reviewer must "
        "confirm it matches the expectation (or correct the gold label — never the other way).", "",
        "## Split", "", "| category | dev | test |", "|---|---|---|",
        *[f"| {c} | {d} | {t} |" for c, (d, t) in sorted(by_cat.items())], "",
        f"## Flagged for human review ({len(flags)})", "",
        "A flag means the compiler and the spec-derived expectation disagree. Decide per item "
        "whether the expectation (gold) or the compiler is wrong; compiler bugs become issues.", "",
    ]
    for rid, text, item_flags in flags:
        lines.append(f"- **{rid}** `{text}`")
        lines += [f"  - {f}" for f in item_flags]
    (OUT / "REVIEW.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"drafted {len(rows)} requests, {len(flags)} flagged")
    for rid, text, item_flags in flags:
        print(f"  {rid} {text!r}: {'; '.join(item_flags)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
