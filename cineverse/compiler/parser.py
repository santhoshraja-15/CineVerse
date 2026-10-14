"""Recursive-descent parser: one procedure per non-terminal, LL(2) only at HEDGE, panic-mode
recovery so every request yields an AST.

    request     ::= [ clause { [ SEP ] clause } ] EOF
    clause      ::= limit | diversity | constraint | exclusion | preference
    limit       ::= LIMIT [ NUMBER ] [ ITEM ]  |  NUMBER ITEM
    diversity   ::= DIVERSE [ ITEM ]
    constraint  ::= [ HEDGE ] [ FIELD ] comparison [ UNIT ]
    comparison  ::= CMP quantity | BETWEEN quantity ( SEP("and") | TO ) quantity | DECADE
    quantity    ::= NUMBER [ UNIT ]
    exclusion   ::= [ HEDGE ] ( NEG_HARD | NEG_SOFT ) target { OR target }
    preference  ::= [ HEDGE | STRICT ] term { [ OR ] term } [ ITEM ]
    term/target ::= GENRE | DESCRIPTOR | WORD

Node ids are assigned in pre-order. Separators before the first or after the last clause, and
repeated separators, are skipped without a diagnostic.
Spec: CineVerse_Compiler_Frontend_Specification §4.
"""

from __future__ import annotations

from typing import Literal, cast

from cineverse.compiler.ast import (
    Clause,
    ConstraintClause,
    DescriptorTerm,
    DiversityClause,
    ErrorNode,
    ExclusionClause,
    GenreTerm,
    LimitClause,
    NumberNode,
    PreferenceClause,
    RequestNode,
    Term,
)
from cineverse.compiler.diagnostics import Diagnostic, make
from cineverse.compiler.lexer import Token, TokenType

T = TokenType
FIRST = {
    "limit": {T.LIMIT, T.NUMBER},
    "diversity": {T.DIVERSE},
    "constraint": {T.HEDGE, T.FIELD, T.CMP, T.BETWEEN, T.DECADE},
    "exclusion": {T.NEG_HARD, T.NEG_SOFT, T.HEDGE},
    "preference": {T.HEDGE, T.STRICT, T.GENRE, T.DESCRIPTOR, T.WORD},
}
FIRST_CLAUSE = set().union(*FIRST.values())
SYNC = FIRST_CLAUSE | {T.SEP, T.EOF}
TERMS = {T.GENRE, T.DESCRIPTOR, T.WORD}
COMPARISON = {T.CMP, T.BETWEEN, T.DECADE}


class _Unexpected(Exception):
    """Raised inside a clause procedure; parse_request recovers from the clause start."""


class Parser:
    def __init__(self, tokens: list[Token], source: str) -> None:
        self.tokens = [t for t in tokens if t.type is not T.FILLER]
        end = len(source)
        self.tokens.append(Token(T.EOF, "", None, (end, end)))
        self.source = source
        self.pos = 0
        self.next_id = 0
        self.diagnostics: list[Diagnostic] = []

    # ------------------------------------------------------------------ helpers

    def peek(self, k: int = 0) -> Token:
        return self.tokens[min(self.pos + k, len(self.tokens) - 1)]

    def at(self, *types: TokenType) -> bool:
        return self.peek().type in types

    def advance(self) -> Token:
        tok = self.peek()
        if tok.type is not T.EOF:
            self.pos += 1
        return tok

    def expect(self, *types: TokenType) -> Token:
        if not self.at(*types):
            raise _Unexpected
        return self.advance()

    def new_id(self) -> int:
        node_id = self.next_id
        self.next_id += 1
        return node_id

    def span_from(self, start: int) -> tuple[int, int]:
        return (self.tokens[start].span[0], self.tokens[self.pos - 1].span[1])

    # ------------------------------------------------------------------ request

    def parse_request(self) -> RequestNode:
        node_id = self.new_id()
        clauses: list[Clause] = []
        while True:
            while self.at(T.SEP):
                self.advance()
            if self.at(T.EOF):
                break
            clause = self.parse_clause()
            if clause is not None:
                clauses.append(clause)
        return RequestNode(tuple(clauses), self.source, (0, len(self.source)), node_id)

    def parse_clause(self) -> Clause | None:
        tok = self.peek()
        start, saved_id = self.pos, self.next_id
        try:
            if tok.type is T.NUMBER and self.peek(1).type is not T.ITEM:
                self.advance()
                self.diagnostics.append(make("P002", span=tok.span, n=tok.lexeme))
                return None
            if tok.type in FIRST["limit"]:
                return self.parse_limit()
            if tok.type is T.DIVERSE:
                return self.parse_diversity()
            if tok.type is T.HEDGE:  # the only LL(2) decision
                nxt = self.peek(1).type
                if nxt in {T.FIELD} | COMPARISON:
                    return self.parse_constraint()
                if nxt in (T.NEG_HARD, T.NEG_SOFT):
                    return self.parse_exclusion()
                return self.parse_preference()
            if tok.type in FIRST["constraint"]:
                return self.parse_constraint()
            if tok.type in FIRST["exclusion"]:
                return self.parse_exclusion()
            if tok.type in FIRST["preference"]:
                return self.parse_preference()
        except _Unexpected:
            pass
        self.pos, self.next_id = start, saved_id
        return self.recover()

    def recover(self) -> ErrorNode:
        """Panic mode: consume at least one token, then up to a synchronising token."""
        start = self.pos
        node_id = self.new_id()
        self.advance()
        while not self.at(*SYNC):
            self.advance()
        span = self.span_from(start)
        text = self.source[span[0]:span[1]]
        self.diagnostics.append(make("P001", span=span, text=text))
        return ErrorNode(text, span, node_id)

    # ------------------------------------------------------------------ clauses

    def parse_limit(self) -> LimitClause:
        start, node_id = self.pos, self.new_id()
        n: int | None = None
        if self.at(T.NUMBER):
            n = int(self.advance().value)  # type: ignore[call-overload]
            self.expect(T.ITEM)
        else:
            self.expect(T.LIMIT)
            if self.at(T.NUMBER):
                n = int(self.advance().value)  # type: ignore[call-overload]
            if self.at(T.ITEM):
                self.advance()
        return LimitClause(n, self.span_from(start), node_id)

    def parse_diversity(self) -> DiversityClause:
        start, node_id = self.pos, self.new_id()
        self.expect(T.DIVERSE)
        if self.at(T.ITEM):
            self.advance()
        return DiversityClause(self.span_from(start), node_id)

    def parse_constraint(self) -> ConstraintClause:
        start, node_id = self.pos, self.new_id()
        hedged = bool(self.at(T.HEDGE) and self.advance())
        field_raw = self.advance().lexeme if self.at(T.FIELD) else None
        op, values = self.parse_comparison()
        unit_raw = self.advance().lexeme if self.at(T.UNIT) else None
        return ConstraintClause(field_raw, op, values, unit_raw, hedged,  # type: ignore[arg-type]
                                self.span_from(start), node_id)

    def parse_comparison(self) -> tuple[str, tuple[NumberNode, ...]]:
        tok = self.expect(*COMPARISON)
        if tok.type is T.CMP:
            return str(tok.value), (self.parse_quantity(),)
        if tok.type is T.BETWEEN:
            low = self.parse_quantity()
            if self.at(T.SEP) and self.peek().lexeme == "and":
                self.advance()
            else:
                self.expect(T.TO)
            return "BETWEEN", (low, self.parse_quantity())
        lo, hi = cast(tuple[int, int], tok.value)
        return "DECADE", (NumberNode(lo, None, tok.span, self.new_id()),
                          NumberNode(hi, None, tok.span, self.new_id()))

    def parse_quantity(self) -> NumberNode:
        start, node_id = self.pos, self.new_id()
        number = self.expect(T.NUMBER)
        unit = self.advance().lexeme if self.at(T.UNIT) else None
        return NumberNode(number.value, unit, self.span_from(start), node_id)  # type: ignore[arg-type]

    def parse_exclusion(self) -> ExclusionClause:
        start, node_id = self.pos, self.new_id()
        hedged = bool(self.at(T.HEDGE) and self.advance())
        neg = self.expect(T.NEG_HARD, T.NEG_SOFT)
        targets = [self.parse_term()]
        while self.at(T.OR) and self.peek(1).type in TERMS:
            self.advance()
            targets.append(self.parse_term())
        strength: Literal["HARD", "SOFT"] = "HARD" if neg.type is T.NEG_HARD else "SOFT"
        return ExclusionClause(tuple(targets), strength, hedged, self.span_from(start), node_id)

    def parse_preference(self) -> PreferenceClause:
        start, node_id = self.pos, self.new_id()
        modifier = "NONE"
        if self.at(T.HEDGE, T.STRICT):
            modifier = "HEDGE" if self.advance().type is T.HEDGE else "STRICT"
        terms = [self.parse_term()]
        has_or = False
        while self.at(*TERMS) or (self.at(T.OR) and self.peek(1).type in TERMS):
            if self.at(T.OR):
                self.advance()
                has_or = True
            terms.append(self.parse_term())
        if self.at(T.ITEM):
            self.advance()
        return PreferenceClause(tuple(terms), modifier, has_or,  # type: ignore[arg-type]
                                self.span_from(start), node_id)

    def parse_term(self) -> Term:
        tok = self.expect(*TERMS)
        node_id = self.new_id()
        if tok.type is T.GENRE:
            return GenreTerm(tok.lexeme, tuple(tok.value), tok.span, node_id)  # type: ignore[arg-type]
        return DescriptorTerm(tok.lexeme, tok.span, node_id)


def parse(tokens: list[Token], source: str) -> tuple[RequestNode, list[Diagnostic]]:
    """Tokens (FILLER included; removed here) to an AST plus P001/P002 diagnostics."""
    parser = Parser(tokens, source)
    return parser.parse_request(), parser.diagnostics
