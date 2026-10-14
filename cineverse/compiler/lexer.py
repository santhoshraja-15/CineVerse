"""Lexer: request text to typed tokens with [start, end) spans into the original text.

Longest match over phrases of 4, 3, 2, then 1 words; precedence genre > NEG_SOFT > other closed
tables > DESCRIPTOR > FILLER > WORD. FILLER tokens are returned (for the trace) and removed by the
parser. The token list carries no EOF; the parser appends it.
Spec: CineVerse_Compiler_Frontend_Specification §3.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, cast

from cineverse.compiler import lexicon
from cineverse.compiler.diagnostics import Diagnostic, make
from cineverse.compiler.registry import DomainRegistry


class TokenType(Enum):
    GENRE = "GENRE"
    DESCRIPTOR = "DESCRIPTOR"
    NEG_HARD = "NEG_HARD"
    NEG_SOFT = "NEG_SOFT"
    HEDGE = "HEDGE"
    STRICT = "STRICT"
    CMP = "CMP"
    BETWEEN = "BETWEEN"
    TO = "TO"
    NUMBER = "NUMBER"
    DECADE = "DECADE"
    UNIT = "UNIT"
    FIELD = "FIELD"
    LIMIT = "LIMIT"
    ITEM = "ITEM"
    DIVERSE = "DIVERSE"
    SEP = "SEP"
    OR = "OR"
    FILLER = "FILLER"
    WORD = "WORD"
    EOF = "EOF"


@dataclass(frozen=True, slots=True)
class Token:
    type: TokenType
    lexeme: str  # as in source (lower-cased)
    value: object  # normalised value
    span: tuple[int, int]  # [start, end) in the ORIGINAL text

    def display(self) -> str:
        """Printed form used by the Example JSON: TYPE(lexeme->value)[s,e); FILLER has no span."""
        t = self.type
        if t is TokenType.FILLER:
            return f"FILLER({self.lexeme})"
        body = self.lexeme
        if t is TokenType.GENRE:
            body += "->" + ",".join(self.value)  # type: ignore[arg-type]
        elif t is TokenType.CMP:
            body += f"->'{self.value}'"
        elif t is TokenType.FIELD:
            body += f"->{self.value}"
        elif t is TokenType.DECADE:
            lo, hi = cast(tuple[int, int], self.value)
            body += f"->{lo}..{hi}"
        return f"{t.value}({body})[{self.span[0]},{self.span[1]})"

    def to_dict(self) -> dict[str, Any]:
        value = list(self.value) if isinstance(self.value, tuple) else self.value
        return {"type": self.type.value, "lexeme": self.lexeme, "value": value,
                "span": list(self.span)}


WORD_RE = re.compile(r"[a-z0-9]+(?:[-'.][a-z0-9]+)*|[,;]")
NUMBER_RE = re.compile(r"^\d+(?:\.\d+)?$")
DECADE_RE = re.compile(r"^(?:(\d{2})|(\d{2})(\d)0)'?s$")
MAX_PHRASE = 4
TRANSLATE = {
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
    "‘": "'", "’": "'", "‛": "'", "“": '"', "”": '"',
}


def normalise(text: str) -> str:
    """Lower-case and unify dashes/quotes, keeping length so spans map 1:1 (step 2)."""
    out = []
    for ch in text:
        ch = TRANSLATE.get(ch, ch)
        low = ch.lower()
        out.append(low if len(low) == 1 else ch)
    return "".join(out)


def phrase_table(registry: DomainRegistry) -> dict[str, tuple[TokenType, object]]:
    """Phrase -> (type, value), inserted in precedence order so the first table wins."""
    table: dict[str, tuple[TokenType, object]] = {}

    def add(phrases: object, ttype: TokenType, value: object = None) -> None:
        if isinstance(phrases, dict):
            items = list(phrases.items())
        else:
            items = [(p, value) for p in cast(tuple[str, ...], phrases)]
        for phrase, v in items:
            table.setdefault(phrase, (ttype, v))

    add(dict(registry.genre_lexemes), TokenType.GENRE)
    add(lexicon.NEG_SOFT, TokenType.NEG_SOFT, "SOFT")
    add(lexicon.NEG_HARD, TokenType.NEG_HARD, "HARD")
    add(lexicon.HEDGE, TokenType.HEDGE, "SOFT")
    add(lexicon.STRICT, TokenType.STRICT, "HARD")
    add(lexicon.CMP, TokenType.CMP)
    add(lexicon.BETWEEN, TokenType.BETWEEN, "BETWEEN")
    add(lexicon.TO, TokenType.TO, "TO")
    add(lexicon.FIELD, TokenType.FIELD)
    add({u: u for u in registry.config.units}, TokenType.UNIT)
    add(lexicon.LIMIT, TokenType.LIMIT, "LIMIT")
    add(lexicon.ITEM, TokenType.ITEM, "ITEM")
    add(lexicon.DIVERSE, TokenType.DIVERSE, "DIVERSE")
    add(lexicon.SEP, TokenType.SEP, "SEP")
    add(lexicon.OR, TokenType.OR, "OR")
    add({d: d for d in lexicon.DESCRIPTORS}, TokenType.DESCRIPTOR)
    add(lexicon.FILLER, TokenType.FILLER, None)
    return table


def _decade(word: str) -> tuple[int, int] | None:
    m = DECADE_RE.match(word)
    if not m:
        return None
    if m.group(1) is not None:
        two = int(m.group(1))
        if two % 10:
            return None
        start = (2000 if two < 30 else 1900) + two
    else:
        start = int(m.group(2) + m.group(3) + "0")
    return (start, start + 9)


def _number(word: str) -> int | float | None:
    if NUMBER_RE.match(word):
        return float(word) if "." in word else int(word)
    return lexicon.NUMBER_WORDS.get(word)


def lex(text: str, registry: DomainRegistry) -> tuple[list[Token], list[Diagnostic]]:
    """Steps 1–7 of Frontend Spec §3.2."""
    if not text.strip() or len(text) > registry.max_input_chars:
        return [], [make("S113", span=(0, len(text)), max=registry.max_input_chars)]

    norm = normalise(text)
    diagnostics: list[Diagnostic] = []
    words: list[tuple[str, int, int]] = []
    pos = 0
    for m in WORD_RE.finditer(norm):
        for i in range(pos, m.start()):
            if not norm[i].isspace():
                diagnostics.append(make("L001", span=(i, i + 1), ch=text[i]))
        words.append((m.group(), m.start(), m.end()))
        pos = m.end()
    for i in range(pos, len(norm)):
        if not norm[i].isspace():
            diagnostics.append(make("L001", span=(i, i + 1), ch=text[i]))

    table = phrase_table(registry)
    tokens: list[Token] = []
    i = 0
    while i < len(words):
        for n in range(min(MAX_PHRASE, len(words) - i), 0, -1):
            phrase = " ".join(w for w, _, _ in words[i:i + n])
            start, end = words[i][1], words[i + n - 1][2]
            if phrase in table:
                ttype, value = table[phrase]
                tokens.append(Token(ttype, phrase, value, (start, end)))
                i += n
                break
            if n == 1:
                word = words[i][0]
                decade = _decade(word)
                number = _number(word)
                if decade is not None:
                    tokens.append(Token(TokenType.DECADE, word, decade, (start, end)))
                elif number is not None:
                    tokens.append(Token(TokenType.NUMBER, word, number, (start, end)))
                else:
                    tokens.append(Token(TokenType.WORD, word, word, (start, end)))
                i += 1
    return tokens, diagnostics
