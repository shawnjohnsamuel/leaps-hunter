# ADR 0013: The paper ledger is the year-one output; NAV is configured, never inferred

**Status:** accepted (2026-09-03)

## Context
v7 §17 declares the screener invalid until its rules are tested, and caps every position at
**0.25% of NAV** until 50 comparable out-of-sample observations exist. Day one has zero.

Against real Jan-2028 premiums, that cap puts `N_max = 0` on every permitted structure —
verticals included — at the current NAV. §13.3 rejects the outright, then the spread, then the
trade. This is correct behaviour per Appendix A.2, which is explicit that the answer is a
larger NAV or a different underlying, never a smaller-delta workaround.

Phase 0 then found a second, sharper NAV problem: `get_accounts` returns five accounts and
`get_portfolio` requires one to be named. A test agent choosing on its own landed on an empty
account. NAV feeds §13.3 directly, so **NAV = 0 produces a correct-looking `NO TRADE` on every
name forever** — and since zero-trade days are the expected output, nothing would look wrong.

## Decision
**Feasibility.**
- Emit `min_feasible_nav` per candidate per structure in every rejection, rather than hardcoding
  a NAV band. A rejection reads `CRM 0.65Δ — requires $2.5M at unvalidated cap / $500K
  post-calibration`, and rescales itself as NAV changes or calibration completes.
- **Stage A stays price-blind.** Weighting the watchlist toward cheaper underlyings would let
  share price influence thesis selection — §5 states price is not a mechanism and §19 bans that
  story-selector inversion. Feasibility annotates via `feasible_at_current_nav`; it never
  filters upstream.
- Qualifying-but-infeasible candidates route to the paper ledger. Those observations are the
  §17 cohort that lifts the cap from 0.25% to 1.25%. Year-one paper output is not a consolation
  prize; it is the calibration input that makes the engine live.

**NAV integrity.**
- The account is **configured, not inferred**: `state/config.yaml` carries an explicit
  `portfolio.account_ref` and the engine never selects heuristically, nor falls back to "the
  first" or "the default" without that reference matching.
- A zero or absent NAV **hard-fails** as `NO TRADE — DATA INSUFFICIENT` naming NAV as the
  missing input (§18), rather than flowing into §13.3 to produce arithmetic rejections that
  look like ordinary discipline.
- NAV is read live each run and **never written to disk in either repo**. Only
  `min_feasible_nav`, percentages and contract counts persist — which discloses what the
  thresholds require without disclosing what the account holds.

## Consequences
- The expected year-one output is a disciplined paper record, not trades. This must be stated
  plainly rather than discovered.
- A silent-failure mode that would have been invisible in production is closed by construction.
- `min_feasible_nav` doubles as documentation: the daily log becomes a running record of exactly
  what each threshold unlocks.
