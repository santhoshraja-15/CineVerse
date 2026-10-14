# CineVerse — Compiler Front-End Specification
**Compiler Front-End Specification · v1.0**

Team 14 (Santhoshraja S, Siddharth P, Keshore G) · 2026-10-14 · Status: Draft for team review

---

> **Normative.** This document defines the request language, lexer, grammar, parser, AST, domain registry, semantic rules and diagnostics. Code in `cineverse/compiler/{lexicon,lexer,parser,ast,registry,semantic,diagnostics}.py` must match it. Changes require a spec update first (see Project Control §5).

## Contents
1. Source Language Overview · 2. Domain Registry · 3. Lexer · 4. Grammar and Parser · 5. AST · 6. Semantic Analysis · 7. Diagnostics · 8. Worked Examples · 9. Test Obligations

## 1. Source Language Overview

| Construct | Examples | Compiles to |
|---|---|---|
| Genre preference | "sci-fi", "a mystery", "rom-com" | soft +1 genre preference(s) |
| Required genre | "only comedies", "must be animation" | hard `genre HAS g` |
| Strict alternatives | "only comedy or drama" | soft +1 each, S114 |
| Descriptor | "thoughtful", "time travel", unknown words | soft +1 text preference; part of `semantic_text` |
| Hard exclusion | "no horror", "without musicals" | hard `genre NOT_HAS g` |
| Unverifiable exclusion | "no gore" | soft −1 text, S106 |
| Soft exclusion | "little romance", "not too violent", "ideally no horror" | soft −1 |
| Year | "after 2010", "before 1990", "between 2000 and 2010", "90s" | hard bounds on `year` |
| Rating / votes | "rated at least 4", "at least 100 ratings" | hard bounds on `rating` / `votes` |
| Hedged bound | "preferably after 2000" | soft bound |
| Runtime / language | "under 2 hours" | S112 + S105 (unavailable in CORE) |
| Limit | "top 5", "show me 3", "give me 8 films" | `output.limit` (1–50) |
| Diversity | "diverse", "varied" | `ranking.diversity = "mmr"` if built, else S105 |

## 2. Domain Registry
```yaml
registry_version: "1.0"
genres:                       # canonical -> display name used in embed/semantic text
  Action: action
  Adventure: adventure
  Animation: animation
  Children: children's
  Comedy: comedy
  Crime: crime
  Documentary: documentary
  Drama: drama
  Fantasy: fantasy
  Film-Noir: film noir
  Horror: horror
  IMAX: imax
  Musical: musical
  Mystery: mystery
  Romance: romance
  Sci-Fi: science fiction
  Thriller: thriller
  War: war
  Western: western
genre_aliases:                # lexeme -> list of canonical genres
  sci-fi: [Sci-Fi]
  scifi: [Sci-Fi]
  science fiction: [Sci-Fi]
  sf: [Sci-Fi]
  rom-com: [Romance, Comedy]
  romcom: [Romance, Comedy]
  romantic comedy: [Romance, Comedy]
  animated: [Animation]
  cartoon: [Animation]
  kids: [Children]
  family: [Children]
  noir: [Film-Noir]
  scary: [Horror]
  funny: [Comedy]
  documentaries: [Documentary]
  musicals: [Musical]
  # plurals (comedies, thrillers, mysteries, ...) generated automatically
fields:
  genre:    {type: genre_set, ops: [HAS, NOT_HAS], available: true}
  year:     {type: int,   unit: year,    ops: ["<=", ">="], domain: from_catalog, available: true}
  rating:   {type: float, unit: stars,   ops: ["<=", ">="], domain: [0.5, 5.0],  available: true}
  votes:    {type: int,   unit: ratings, ops: ["<=", ">="], domain: [0, null],   available: true}
  runtime:  {type: int,   unit: minutes, ops: ["<=", ">="], domain: [1, 600],    available: false}
  language: {type: code,  ops: [HAS],    available: false}
units:
  stars: {field: rating, factor: 1}
  ratings: {field: votes, factor: 1}
  votes: {field: votes, factor: 1}
  minutes: {field: runtime, factor: 1}
  mins: {field: runtime, factor: 1}
  hours: {field: runtime, factor: 60}
  hrs: {field: runtime, factor: 60}
limit: {min: 1, max: 50, default: 10}
max_input_chars: 300
```

At load, `DomainRegistry` adds: year domain = [min year, max year] of the catalogue; per-field coverage; `channels.semantic` = index and model load successfully; `ranking.mmr` = diversity module present.

## 3. Lexer
### 3.1 Token

```python
class TokenType(Enum):
    GENRE DESCRIPTOR NEG_HARD NEG_SOFT HEDGE STRICT CMP BETWEEN TO NUMBER DECADE UNIT FIELD
    LIMIT ITEM DIVERSE SEP OR FILLER WORD EOF

@dataclass(frozen=True, slots=True)
class Token:
    type: TokenType
    lexeme: str            # as in source (lower-cased)
    value: object          # normalised value (see table)
    span: tuple[int, int]  # [start, end) in the ORIGINAL text
```

### 3.2 Algorithm

1. Reject empty input or > `max_input_chars` (S113).
2. `norm = text.lower()` with unicode dashes → "-", curly quotes → straight. Length is preserved so spans map 1:1.
3. Scan words with `[a-z0-9]+(?:[-'.][a-z0-9]+)*|[,;]`; other characters produce L001 (INFO) and are skipped.
4. At each position try phrase-lexicon matches of 4, 3, 2, then 1 words (longest match). Phrase lexicon = genre aliases + genre names + plurals + `lexicon.py` tables below.
5. Numbers: digits (`3.5`, `2010`), number words one–twenty; decades `90s`, `1990s`, `80's` → DECADE `(1990, 1999)`.
6. Remaining word: FILLER if in stop list, else WORD.
7. FILLER tokens are kept in the trace but removed before parsing.

### 3.3 Lexicon (`cineverse/compiler/lexicon.py`)

| Type | Lexemes | value |
|---|---|---|
| NEG_HARD | no, not, without, exclude, excluding, avoid, never, none | `"HARD"` |
| NEG_SOFT | little, less, minimal, not too, not much, not very, light on, barely any, low on | `"SOFT"` |
| HEDGE | preferably, ideally, if possible, maybe, rather, would prefer | `"SOFT"` |
| STRICT | only, must be, strictly, just, exclusively | `"HARD"` |
| CMP | under, below, less than, fewer than, before → `<`; at most, no more than, up to → `<=`; over, above, more than, after → `>`; at least, since, from → `>=` | operator string |
| BETWEEN | between | `"BETWEEN"` |
| TO | to, through | `"TO"` |
| FIELD | released, release, year, made, rated, rating, rating of, runtime, long, length, language | field name (`released/release/year/made → year`, `rated/rating → rating`, `runtime/long/length → runtime`) |
| UNIT | see registry `units` | unit name |
| LIMIT | top, show, show me, give me, list, recommend, suggest | `"LIMIT"` |
| ITEM | movie, movies, film, films, picks, titles, options | `"ITEM"` |
| DIVERSE | diverse, varied, variety, different kinds | `"DIVERSE"` |
| SEP | `,` `;` and, with, but, that, which, also | `"SEP"` |
| OR | or | `"OR"` |
| DESCRIPTOR | curated list (~150): moods (dark, uplifting, feel-good, thoughtful, thought-provoking, tense, slow, quirky, emotional, sad, atmospheric, violent, gory, gore, ...), themes (time travel, space, heist, revenge, dystopia, artificial intelligence, twist, twist ending, based on a true story, coming of age, ...) | lemma |
| FILLER | a, an, the, some, something, anything, i, me, my, want, like, would, please, in, of, for, watch, see, find | — |

**Lexicon precedence** when one phrase is in several tables: genre alias/name > NEG_SOFT > other closed tables > DESCRIPTOR > FILLER > WORD. Mood words that are genre aliases ("funny" → Comedy, "scary" → Horror) are therefore GENRE tokens.

Note: "like" is FILLER in v1.0 (the optional "movies like *Title*" construct would make it a token).

## 4. Grammar and Parser
Tokens after FILLER removal. Recursive descent, one function per non-terminal.

```
request     ::= [ clause { [ SEP ] clause } ] EOF
clause      ::= limit | diversity | constraint | exclusion | preference
limit       ::= LIMIT [ NUMBER ] [ ITEM ]  |  NUMBER ITEM
diversity   ::= DIVERSE [ ITEM ]
constraint  ::= [ HEDGE ] [ FIELD ] comparison [ UNIT ]
comparison  ::= CMP quantity
              | BETWEEN quantity ( SEP("and") | TO ) quantity
              | DECADE
quantity    ::= NUMBER [ UNIT ]
exclusion   ::= [ HEDGE ] ( NEG_HARD | NEG_SOFT ) target { OR target }
preference  ::= [ HEDGE | STRICT ] term { [ OR ] term } [ ITEM ]
term        ::= GENRE | DESCRIPTOR | WORD
target      ::= GENRE | DESCRIPTOR | WORD
```

- FIRST sets: limit {LIMIT, NUMBER}; diversity {DIVERSE}; constraint {HEDGE, FIELD, CMP, BETWEEN, DECADE}; exclusion {NEG_HARD, NEG_SOFT, HEDGE}; preference {HEDGE, STRICT, GENRE, DESCRIPTOR, WORD}.
- HEDGE is the only LL(2) point: look at the next token — {FIELD, CMP, BETWEEN, DECADE} → constraint; NEG_SOFT or NEG_HARD → exclusion (hedged NEG_HARD becomes soft in semantics); otherwise preference.
- A trailing ITEM after terms ("sci-fi movies") is consumed and ignored.
- SEP between clauses is optional: a clause ends when the next token cannot continue it, so "sci-fi mystery after 2010" is two clauses. A target list in an exclusion continues only through OR, so "no horror comedy" is an exclusion (Horror) followed by a preference (Comedy).
- An empty token list (after FILLER removal) parses to a `RequestNode` with no clauses; semantic analysis reports S111.
- Error recovery (panic mode): on an unexpected token emit P001 (WARNING) with its span, collect tokens into an `ErrorNode` until a synchronising token — SEP or any token in FIRST(clause) — and continue. A NUMBER that starts no valid clause (not followed by ITEM) → P002 and only that token is skipped.

### 4.1 Parser procedures
| Procedure | Consumes | Returns |
|---|---|---|
| `parse_request()` | whole stream | `RequestNode` |
| `parse_clause()` | dispatch on FIRST sets / LL(2) at HEDGE | one `Clause` |
| `parse_limit()` | `LIMIT [NUMBER] [ITEM]` or `NUMBER ITEM` | `LimitClause` |
| `parse_diversity()` | `DIVERSE [ITEM]` | `DiversityClause` |
| `parse_constraint()` | `[HEDGE] [FIELD] comparison [UNIT]` | `ConstraintClause` |
| `parse_comparison()` | `CMP quantity`, `BETWEEN q and/TO q`, `DECADE` | op + values |
| `parse_exclusion()` | `[HEDGE] NEG_HARD-or-NEG_SOFT target {OR target}` | `ExclusionClause` |
| `parse_preference()` | `[HEDGE-or-STRICT] term {[OR] term} [ITEM]` | `PreferenceClause` (records whether OR occurred) |
| `recover()` | tokens up to a synchronising token | `ErrorNode` + P001 |

`PreferenceClause` gains one field for S13: `has_or: bool`.

## 5. AST
```python
Span = tuple[int, int]

@dataclass(frozen=True, slots=True)
class GenreTerm:       raw: str; genres: tuple[str, ...]; span: Span; node_id: int
class DescriptorTerm:  text: str; span: Span; node_id: int
Term = GenreTerm | DescriptorTerm

class NumberNode:      value: int | float; unit_raw: str | None; span: Span; node_id: int
class PreferenceClause: terms: tuple[Term, ...]; modifier: Literal["NONE","HEDGE","STRICT"]; has_or: bool; span; node_id
class ExclusionClause:  targets: tuple[Term, ...]; strength: Literal["HARD","SOFT"]; hedged: bool; span; node_id
class ConstraintClause: field_raw: str | None; op: Literal["<","<=",">",">=","BETWEEN","DECADE"];
                        values: tuple[NumberNode, ...]; unit_raw: str | None; hedged: bool; span; node_id
class LimitClause:      n: int | None; span; node_id
class DiversityClause:  span; node_id
class ErrorNode:        text: str; span; node_id
Clause = PreferenceClause | ExclusionClause | ConstraintClause | LimitClause | DiversityClause | ErrorNode

class RequestNode:      clauses: tuple[Clause, ...]; source: str; span; node_id
```

`ast.to_dict(node)` produces JSON for golden files and the UI (`{"kind": "GenreTerm", "raw": ..., "span": [s, e], ...}`).

## 6. Semantic Analysis
```python
@dataclass
class Annotation:
    kind: Literal["pref", "constraint", "limit", "diversity", "ignored"]
    field: str | None          # genre/year/rating/votes/runtime/language/text
    op: str | None             # HAS, NOT_HAS, <, <=, >, >=
    value: object              # canonical value(s) after conversion
    polarity: Literal[1, -1] | None
    strictness: Literal["hard", "soft"] | None
    applied: bool              # False when S105 drops it

@dataclass
class SemanticResult:
    ast: RequestNode
    annotations: dict[int, list[Annotation]]   # node_id -> annotations
    diagnostics: list[Diagnostic]
```

Rules, applied in this order:

| ID | Rule |
|---|---|
| S1 | Resolve GenreTerm via aliases/plurals to canonical genres. A WORD that is not a genre stays a DescriptorTerm (S101 INFO only if it looks like a genre, edit distance ≤ 2) |
| S2 | Infer missing field of a ConstraintClause: unit → field via `units`; else integer value in year domain or DECADE → `year`; else S102 ERROR |
| S3 | Type check: op ∈ field.ops (after mapping `<`,`>` to the field's type); value type matches; else S103 ERROR |
| S4 | Range check against field domain → S104 ERROR. Limit outside 1–50 → clamp + S109 WARNING. Missing limit number → default |
| S5 | Unit conversion: value × factor; S112 INFO when factor ≠ 1 |
| S6 | Capability: field `available: false` → S105 WARNING, annotation `applied=False` |
| S7 | Strictness/polarity: PreferenceClause NONE/HEDGE → soft, polarity +1 (genres and descriptors); STRICT + genre → hard `genre HAS g`; STRICT + descriptor → soft (+S106); ExclusionClause HARD (not hedged) + genre → hard `NOT_HAS`; HARD + descriptor → soft polarity −1 + S106; SOFT, or hedged HARD → soft polarity −1; ConstraintClause hedged → soft, else hard; BETWEEN → two annotations (≥ low, ≤ high); DECADE → (≥ start, ≤ end) |
| S8 | (part of S7) hard exclusion of a descriptor is unverifiable → soft, S106 WARNING |
| S9 | Same genre hard HAS and hard NOT_HAS → S107 ERROR (spans of both) |
| S10 | Hard bounds on one field with empty intersection (after converting `<`/`>` on int fields to closed bounds) → S108 ERROR |
| S11 | Soft positive genre that is also hard NOT_HAS → soft dropped, S110 WARNING; soft negative genre that is hard HAS → soft dropped, S110 |
| S12 | No applied preference, constraint or exclusion → S111 ERROR |
| S13 | STRICT clause whose genres are joined by OR ("only comedy or drama") → all its genres soft, S114 WARNING. STRICT with several genres and no OR ("only animated comedies") → one hard HAS per genre |

## 7. Diagnostics
```python
class Severity(Enum): ERROR, WARNING, INFO
@dataclass(frozen=True)
class Diagnostic:
    code: str; severity: Severity; message: str; span: tuple[int, int] | None; hint: str | None
```

| Code | Sev | Message template |
|---|---|---|
| L001 | INFO | Ignored character '{ch}' |
| P001 | WARNING | Could not understand '{text}'; skipped |
| P002 | WARNING | Number {n} has no meaning here |
| S101 | INFO | '{word}' is not a known genre; used as a description |
| S102 | ERROR | Cannot tell what '{text}' refers to (year, rating, votes or runtime?) |
| S103 | ERROR | '{op}' cannot be used with {field} |
| S104 | ERROR | {value} is outside the range of {field} ({lo}–{hi}) |
| S105 | WARNING | {field} is not available in this catalogue; '{text}' was not applied |
| S106 | WARNING | '{text}' cannot be checked exactly; applied as a preference |
| S107 | ERROR | {genre} is both required and excluded |
| S108 | ERROR | No {field} satisfies all conditions |
| S109 | WARNING | Number of results limited to {n} |
| S110 | WARNING | Preference for {genre} overridden by a strict condition |
| S111 | ERROR | Nothing to recommend from; add a genre, mood or condition |
| S112 | INFO | Converted {from} to {to} |
| S113 | ERROR | Request is empty or longer than {max} characters |
| S114 | WARNING | 'only … or …' cannot be applied strictly; used as preferences |
| X201 | WARNING | Semantic search unavailable; results use metadata only |
| X202 | INFO | No movie satisfies all strict conditions |

ERROR stops the driver after semantic analysis. WARNING/INFO are copied into the IR and shown in the UI.

## 8. Worked Examples

Full expected tokens, IR, diagnostics and programs for 25 requests are in `CineVerse_Example_Requests_and_Expected_Outputs.json`. Front-end highlights:

| Request | Key front-end behaviour |
|---|---|
| "thoughtful sci-fi mystery after 2010, little romance, top 5" | No SEP between preference and constraint; field inferred as year (S2); "little" → soft |
| "a funny animated movie, no musicals" | "funny" is a genre alias (precedence); "musicals" plural → Musical; hard NOT_HAS |
| "only comedy or drama" | STRICT with OR → soft + S114 |
| "ideally no horror, mystery" | HEDGE + NEG_HARD → LL(2) picks exclusion; hedged → soft |
| "comedy under 2 hours" | Unit → runtime; 2 h → 120 min (S112); unavailable (S105) |
| "kubrick style space movies" | Unknown WORDs kept as descriptors |
| "thriler from 2005" | Near-genre typo → S101 with hint |
| "drama, stars" | UNIT cannot start a clause → P001, recovery keeps Drama |

## 9. Test Obligations
| Module | Minimum tests |
|---|---|
| `lexer.py` | 40 cases: every token type, longest match, precedence, spans map to original text, number words, decades, L001, S113 |
| `parser.py` | Each production; optional SEP; LL(2) at HEDGE (3 cases); OR in preference and exclusion; P001/P002 recovery; empty input |
| golden ASTs | One per benchmark item (`tests/golden/ast/<id>.json`) |
| `registry.py` | Built from catalogue stats; unavailable fields; alias plurals generated; year domain |
| `semantic.py` | Each rule S1–S13 with ≥ 2 positive and 1 negative case; diagnostic order deterministic (by rule, then span) |
