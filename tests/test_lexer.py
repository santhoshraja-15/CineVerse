"""Spec: Compiler Front-End Specification §3, §9; SRS FR-01, FR-02."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cineverse.compiler.lexer import TokenType, lex, normalise

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = json.loads(
    (ROOT / "docs" / "CineVerse_Example_Requests_and_Expected_Outputs.json").read_text("utf-8")
)["examples"]


def types(text: str, registry) -> list[str]:
    return [t.type.value for t in lex(text, registry)[0]]


def first(text: str, registry):
    return lex(text, registry)[0][0]


@pytest.mark.parametrize("ex", EXAMPLES, ids=[e["id"] for e in EXAMPLES])
def test_example_token_sequences(ex, registry):
    """Every `tokens` field of the Example JSON."""
    tokens, _ = lex(ex["text"], registry)
    assert [t.display() for t in tokens] == ex["expected"]["tokens"]


@pytest.mark.parametrize(
    ("text", "ttype", "value"),
    [
        ("sci-fi", "GENRE", ("Sci-Fi",)),
        ("thoughtful", "DESCRIPTOR", "thoughtful"),
        ("without", "NEG_HARD", "HARD"),
        ("light on", "NEG_SOFT", "SOFT"),
        ("if possible", "HEDGE", "SOFT"),
        ("must be", "STRICT", "HARD"),
        ("no more than", "CMP", "<="),
        ("between", "BETWEEN", "BETWEEN"),
        ("through", "TO", "TO"),
        ("3.5", "NUMBER", 3.5),
        ("1980s", "DECADE", (1980, 1989)),
        ("hrs", "UNIT", "hrs"),
        ("released", "FIELD", "year"),
        ("give me", "LIMIT", "LIMIT"),
        ("films", "ITEM", "ITEM"),
        ("different kinds", "DIVERSE", "DIVERSE"),
        ("but", "SEP", "SEP"),
        ("or", "OR", "OR"),
        ("please", "FILLER", None),
        ("kubrick", "WORD", "kubrick"),
    ],
)
def test_every_token_type(text, ttype, value, registry):
    tok = first(text, registry)
    assert (tok.type.value, tok.value) == (ttype, value)


def test_longest_match_science_fiction_is_one_token(registry):
    tok = first("science fiction", registry)
    assert tok.type is TokenType.GENRE and tok.span == (0, 15)


def test_not_too_is_soft_never_hard(registry):
    assert types("not too dark", registry) == ["NEG_SOFT", "DESCRIPTOR"]


def test_less_than_beats_less(registry):
    assert types("less than 3", registry) == ["CMP", "NUMBER"]
    assert types("less romance", registry) == ["NEG_SOFT", "GENRE"]


def test_genre_alias_beats_descriptor(registry):
    """Precedence: 'funny' and 'scary' are GENRE tokens."""
    assert first("funny", registry).value == ("Comedy",)
    assert first("scary", registry).value == ("Horror",)


def test_alias_expands_to_two_genres(registry):
    assert first("romantic comedy", registry).value == ("Romance", "Comedy")


def test_plurals_generated(registry):
    for word, genre in [("comedies", "Comedy"), ("thrillers", "Thriller"),
                        ("mysteries", "Mystery"), ("westerns", "Western")]:
        assert first(word, registry).value == (genre,)


@pytest.mark.parametrize(("word", "value"), [("one", 1), ("seven", 7), ("twenty", 20)])
def test_number_words(word, value, registry):
    tok = first(word, registry)
    assert tok.type is TokenType.NUMBER and tok.value == value


@pytest.mark.parametrize(
    ("word", "decade"), [("90s", (1990, 1999)), ("80's", (1980, 1989)),
                         ("1970s", (1970, 1979)), ("00s", (2000, 2009))]
)
def test_decades(word, decade, registry):
    tok = first(word, registry)
    assert tok.type is TokenType.DECADE and tok.value == decade


def test_spans_index_the_original_text(registry):
    text = "Only  COMEDIES, please!"
    tokens, _ = lex(text, registry)
    assert [text[s:e] for s, e in (t.span for t in tokens)] == ["Only", "COMEDIES", ",", "please"]


def test_unicode_dash_normalised_with_same_length(registry):
    text = "sci‐fi"  # U+2010 hyphen
    assert len(normalise(text)) == len(text)
    assert first(text, registry).value == ("Sci-Fi",)


def test_ignored_characters_give_l001_and_are_skipped(registry):
    tokens, diags = lex("sci-fi ★★", registry)
    assert [t.type.value for t in tokens] == ["GENRE"]
    assert [(d.code, d.span) for d in diags] == [("L001", (7, 8)), ("L001", (8, 9))]
    assert diags[0].severity.value == "INFO"


@pytest.mark.parametrize("text", ["", "   ", "x" * 301])
def test_empty_or_too_long_gives_s113(text, registry):
    tokens, diags = lex(text, registry)
    assert tokens == [] and [d.code for d in diags] == ["S113"]


def test_300_characters_is_accepted(registry):
    tokens, diags = lex("a" * 300, registry)
    assert diags == [] and len(tokens) == 1


def test_filler_kept_for_trace(registry):
    assert types("i want a comedy", registry) == ["FILLER", "FILLER", "FILLER", "GENRE"]


def test_unknown_words_are_words_not_errors(registry):
    tokens, diags = lex("wes anderson vibes", registry)
    assert [t.type for t in tokens] == [TokenType.WORD] * 3 and diags == []


def test_hyphenated_and_apostrophe_words_stay_whole(registry):
    tokens, _ = lex("kubrick's mind-bending", registry)
    assert [t.lexeme for t in tokens] == ["kubrick's", "mind-bending"]


def test_lexer_is_pure(registry):
    """LA-05: same input, same output."""
    assert lex("dark sci-fi after 2010", registry) == lex("dark sci-fi after 2010", registry)
