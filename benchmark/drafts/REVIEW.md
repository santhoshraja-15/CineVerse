# H1 benchmark draft — review sheet

95 drafted requests (R026–R120). **Status: draft — not used by any test or evaluation until approved and merged into `benchmark/requests.jsonl`.**

Each request has a hand-written expectation from the specification, written independently of the compiler. `gold_ir` is the compiler's *proposal*; a reviewer must confirm it matches the expectation (or correct the gold label — never the other way).

## Split

| category | dev | test |
|---|---|---|
| combined | 2 | 5 |
| descriptor_only | 3 | 5 |
| hard_exclusion | 3 | 5 |
| hedged | 2 | 6 |
| invalid | 6 | 10 |
| limit | 2 | 6 |
| multi_genre | 3 | 5 |
| rating_votes | 2 | 6 |
| single_genre | 3 | 5 |
| soft_exclusion | 2 | 6 |
| year | 2 | 6 |

## Flagged for human review (0)

A flag means the compiler and the spec-derived expectation disagree. Decide per item whether the expectation (gold) or the compiler is wrong; compiler bugs become issues.


## Caveat on independence

The expectations and the compiler were written by the same author (the assistant), so agreement
between them is weak evidence. A team member who did not build the front end should review every
item (Evaluation Plan §2: cross-authoring).

## Coverage observations (spec-correct, but worth a team decision)

These requests behave exactly as the v1.0 grammar specifies, yet a user would not expect a warning.
Changing them is a spec change (Project Control §5: all three members, CHANGELOG, golden review).

| Request | What happens | Why | Possible change |
|---|---|---|---|
| `i want to watch a musical` | P001 on "to" | "to" is the TO token (for "between 1 to 3"), which cannot start a clause | Treat a TO that starts no BETWEEN as FILLER |
| `comedies from the 80s` | P001 on "from" | "from" is CMP (>=) and needs a NUMBER, not a DECADE | Allow `CMP DECADE` (">= start") or `from DECADE` = the decade |
| `two romantic comedies` | P002 on "two" | A number is a limit only when followed by ITEM ("two movies") | Accept `NUMBER GENRE` as a limit + preference |
