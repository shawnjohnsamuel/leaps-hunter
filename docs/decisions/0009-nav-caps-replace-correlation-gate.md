# ADR 0009: NAV-based risk caps replace the portfolio-correlation gate

**Status:** accepted (2026-09-03) · **Supersedes:** [ADR 0006](0006-crowding-counts-options-only.md)

## Context
v6 §5.9 auto-rejected a candidate already held, and rejected a third options position
expressing the same thesis. ADR 0006 amended it on day one because the original rule counted
legacy *equity* holdings toward crowding and blocked the entire active universe.

That amendment fixed a symptom. The gate was still categorical: a binary reject standing in for
a question about concentration that is inherently continuous.

## Decision
Retire the correlation gate. Concentration is enforced by v7 §14's maximum-loss caps, expressed
as % of total NAV —

| Exposure | Cap |
|---|---|
| One issuer | 1.50% |
| One correlated mechanism | 3.00% |
| Entire LEAPS premium book | 8.00% |

— together with §15's requirement that both `Var(Π_new) ≤ Var(Π_old)` and
`ES_95%(Π_new) ≤ ES_95%(Π_old)` over a 21-trading-day horizon with full option repricing.

## Rationale
A cap answers "how much more of this risk can the book carry" with a number; a gate answers it
with a categorical no calibrated to nothing. §14's caps also make the equity-vs-options
distinction ADR 0006 introduced unnecessary — existing exposure enters the covariance matrix by
its actual contribution, whatever instrument carries it.

## Consequences
- **"Already held" is no longer an automatic reject.** It becomes an input: existing exposure
  raises `Var(Π)` and `ES_95%`, and the §15 tests reject only when it genuinely should.
- The gate can no longer block a universe by accident, which is what triggered ADR 0006.
- This depends on §15 being implemented. Until the portfolio engine exists (Phase 3), issuer
  and mechanism caps apply but the joint variance test is trivially satisfied by an empty book
  — a real limitation to state in the report rather than paper over.
- Sleeve percentages remain prohibited as a sizing unit (§14): always total-NAV maximum loss,
  contract count, and correlated exposure.
