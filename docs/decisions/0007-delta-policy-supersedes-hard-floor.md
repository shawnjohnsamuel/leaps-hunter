# ADR 0007: v7's delta policy supersedes the hard ≥60Δ floor

**Status:** accepted (2026-09-03) · **Supersedes:** [ADR 0003](0003-hard-delta-floor-60.md)

## Context
ADR 0003 made ≥60Δ a hard disqualifier because both parent frameworks *scored* deep-ITM
structures without ever *gating* them, and a competing version had historically produced OTM
strikes that violated the framework's own intent. A rule that matters only when it is
inconvenient must be a gate, not a score.

v7 §13.1 reaches the same destination by a different road. It requires the selected delta to
**emerge from the net-return and portfolio-risk model** used to size the trade, with bands
acting as guardrails on that optimization rather than as defaults:

| Environment | Permitted |
|---|---|
| Macro hard gate active (§6.1) | no new long LEAPS |
| Restricted regime (R ≥ 3) | 0.70–0.85, or validated verticals |
| Normal regime | 0.60–0.85 |
| Higher-convexity exception | 0.55–0.70 **only if** §15 variance and ES tests pass |
| Below 0.55 | prohibited for ordinary single-name LEAPS |

## Decision
Adopt §13.1 as written. The categorical 60Δ floor is retired.

## Rationale
v7 Appendix A.1 is explicit that the ≥0.55 floor is a *risk-control decision, not a calibrated
optimum*, and that prior analysis favouring 0.40–0.60 used single-name assumptions, ignored
portfolio covariance, and was never validated out of sample. Freezing 60Δ as doctrine would
preserve ADR 0003's virtue (no silent OTM drift) at the cost of v7's core claim — that
structure selection is an optimization under constraints, not a preference.

§19 bans making deep-ITM a universal answer for the same reason it bans making 0.45–0.60 a
default: both substitute a fixed opinion for a model.

## Consequences
- **In practice, behaviour is unchanged until Phase 3.** The convexity exception is reachable
  only through §15's variance and expected-shortfall tests, which do not exist until the
  portfolio engine is built. Until then the effective floor is 0.60.
- Sub-0.55 remains prohibited outright, so ADR 0003's actual failure mode stays closed.
- The floor may only be relaxed by the evidence path in Appendix A.1 — §17 requirements 1, 2
  and 5 run across the 0.40–0.90 range — never by argument. Any change is a §21 entry.
