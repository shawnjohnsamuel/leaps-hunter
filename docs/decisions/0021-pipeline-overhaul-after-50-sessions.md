# ADR 0021: Pipeline overhaul after 50 sessions

**Status:** accepted (2026-11-03) · **Amends:** §10 (pattern inputs), §11 (how two dimensions
are scored), §12.1 (open-interest floor), §9 (M2 threshold), §17 (paper-ledger lifecycle),
[ADR 0013](0013-paper-ledger-and-nav-integrity.md), [ADR 0014](0014-macro-fetch-desktop-only.md)

## Context

Fifty daily records (2026-09-03 to 2026-11-03), about 600 name-sessions. The funnel:

| Stopped at | Name-sessions |
|---|---|
| §10, no pattern qualifies | 389 |
| §7, earnings inside 14 days | 79 |
| §10, pattern qualifies but confirmation unresolved | 38 |
| §11, a sub-gate minimum | 34 |
| §11, total below threshold | 17 |
| §7, governance | 17 |
| No screen (macro state stale, `stop` band) | 14 |
| §13.3, infeasible at current NAV | 2 (MU, 11-02 and 11-03) |

Five things in that table are structural rather than the market saying no.

1. **Only one of §10's four patterns could ever clear.** `panic` cleared 53 times. `breakout`,
   `quiet_inflection` and `bottleneck_expansion` cleared zero times, because their judgment inputs
   (a multiple-expansion ratio, an accelerating-metrics count, backlog-vs-revenue growth) were
   never supplied, and a missing input fails closed. The 38 "unresolved" rows are these. Bottleneck
   was also unclearable by construction: it required §12's option-valuation result at §10, but §12
   runs after §10 and §11.
2. **Two §11 sub-gates were scored by impression, and missed in noisy ways.** `invalidation_clarity`
   (minimum 5 of 5) came out 4 for every M2 name because §9 calls M2's trigger "material"
   deceleration with no number. `option_implementation` (minimum 10) came out anywhere from 3 to 7
   for the same thin chain on different days.
3. **The open-interest floor of 500 rejected most mid-cap LEAP chains** at the 0.70–0.85 delta
   strikes (CEG, PANW, CRWD, ZS, MDB: 13–211). For a position of one to a few contracts, the spread,
   quote-age and volume vetoes measure execution cost. Open interest well above the position size
   adds little.
4. **The §17 cap could never lift.** Nothing filled in an entry's `realized_outcome`, so the
   50-observation count stayed at zero forever. MU was also logged twice for one episode.
5. **Macro state went 16 days stale** and stopped two sessions. The desktop scheduled task that
   refreshed it launched in the app's `default` permission mode and stopped at its first command
   on 2026-10-18 and 2026-10-25, while showing "succeeded".

None of this changes the binding constraint behind the only two full clears. MU's Jan-2028 $600 call
cost about $37,750 a contract, roughly 100% of the account's NAV. The unvalidated cap allows
0.25% ($94), and the calibrated 1.25% cap would allow about $470. Appendix A.2 already says what
this means: the answer is a larger NAV or a different underlying, not a looser screen. This ADR
makes the screen honest and lets the ledger calibrate. It does not make an infeasible trade
feasible.

## Decision

**Pattern inputs (§10).**
- `breakout`: `engine.patterns.multiple_expansion_ratio` computes it from the price change and the
  NTM EPS revision over the same 60 days: `((P_now/P_60d) / (1 + rev) − 1) / rev`. Unresolved when
  NTM is unavailable or estimates didn't rise.
- `quiet_inflection`: relative underperformance against the name's `sector_etf` over 42 sessions
  and a range-bound test (high/low band ≤ 15% over 42 sessions) are computed. Both numbers are
  `[ASSUMPTION]`, since §10 names neither. The accelerating-metrics count comes from filings, cached
  by `weekly-review` in `pattern_inputs`.
- `bottleneck_expansion`: backlog inputs are cached the same way. `option_valuation_passed=None` now
  means **deferred to §12**, which runs that test before any CANDIDATE. `False` still blocks.

**Scoring (§11).** `option_implementation` = `engine.scoring.option_implementation_score`: 10 when
the DTE, spread, open-interest and volume vetoes all pass, 3 less per failure, up to 5 more for a
tight spread, deep open interest and a clean IV check. `invalidation_clarity` scores 5 when the kill
switch names numbers. `kill_switch_thresholds.M2` supplies M2's: growth down at least 5 points per
report for 2 reports.

**Open interest (§12.1).** `open_interest_min` 500 → 250. The quoted-spread (6%), quote-age (60s)
and 20-day-volume (10) vetoes are unchanged.

**Paper ledger (§17).** `engine.ledger`: one entry per episode (a re-clear reconfirms the open
entry), weekly marks at the contract's bid by `weekly-review`, a close at 180 days or on a kill
switch, and calibration counts closed entries only. MU's 2026-11-03 entry becomes a reconfirmation
of 2026-11-02's. `compute_feasibility` also reports `contract_pct_of_nav` and
`min_feasible_nav_calibrated`.

**Macro refresh.** `scripts/macro_refresh.py` does the skill's steps 1, 1a, 2 and 3 through the same
engine calls, run by a GitHub Action in the data repo on weekdays at 14:00 UTC and Sundays at
13:30 UTC. GitHub's runners aren't behind the cloud-routine egress block. The NYSE breadth list
(step 1b, Massive) stays a by-hand desktop step, about monthly.

**Not changed, on purpose.** The 80 restricted threshold, the 14-day earnings blackout, the panic
pattern's 10–20% window, every NAV cap, and the delta bands. R has been 4 every week since
September, so 80 is in effect the permanent bar. MU cleared it at 81. The sizing caps are the
user's risk decision, not a calibration question this ADR can settle.

## Consequences

- Three more patterns can clear. Expect more names to reach §11, and more paper candidates,
  without any change to what a real CANDIDATE requires at §12–§15.
- The §21 version log: these are threshold changes. The calibration ledger had no closed entries,
  so no measured out-of-sample effect exists to reset.
- Macro staleness should read `current` every day. A `flag` now means the Action failed.
- Until `ALPHA_VANTAGE_API_KEY` is set as an Actions secret on the data repo, the Action skips the
  NTM step and keeps the cached values. Panic confirmation reads that cache, so the secret matters.
