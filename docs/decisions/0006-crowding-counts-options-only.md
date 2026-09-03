# ADR 0006: Portfolio-crowding gate counts only options/LEAPS positions

**Status:** ~~accepted (2026-07-08, after screener run 1)~~ — **SUPERSEDED by
[ADR 0009](0009-nav-caps-replace-correlation-gate.md)** on 2026-09-03 during the v7 migration:
v7 §14 NAV caps and §15 portfolio tests replace the correlation gate entirely. Retained as
design history; the reasoning below explains why the rule existed, which the superseding ADR
builds on.

## Context
v6 §5.9 as first written rejected any new position when "≥2 existing positions already
express the same thesis/sub-sector." On the framework's first run against the real
portfolio, two legacy **equity** holdings in enterprise software (NOW, CRM) tripped the
rule, auto-rejecting every SaaS candidate — including the day's two most genuine
dislocations (INTU at −66% from high / 17x earnings; ADBE at −42% / 12.7x). The gate
built to prevent concentration was instead blocking the framework's entire active
hunting ground.

## Decision
Only **options/LEAPS positions** count toward the same-thesis crowding limit. Equity
holdings are surfaced as exposure context in the report but do not block. The other
prong is unchanged: a candidate whose ticker is already held (equity *or* options) is
still rejected as a new entry ("manage existing position").

## Rationale
The risk the gate exists for is leveraged, correlated LEAPS blowing up together —
several long-dated calls on the same thesis all decaying and drawing down in the same
regime. Small unleveraged equity positions carry a different (and far smaller) tail, and
counting them makes the gate's behavior depend on portfolio history rather than the risk
being added. The strictest reading was tried first and failed observably within one run;
this amendment was a human ruling, not a silent loosening (options considered: keep
as-is; options-only; in-session materiality threshold — options-only chosen as the
cleanest line that never needs position sizes).

## Consequences
- Spec bumped to **v6.1**; Lessons Ledger entry added — the first production lesson to
  change a rule, one day after v6.0 was tagged.
- The 2026-07-08 screen was re-run under the amended rule (rev 2 of that day's report);
  the original rev-1 verdict is preserved in the private data repo's git history.
