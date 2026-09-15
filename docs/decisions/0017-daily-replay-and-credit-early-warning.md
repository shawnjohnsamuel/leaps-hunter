# ADR 0017: Replay the weekly gates day by day; add a daily credit early warning

**Status:** accepted (2026-09-15) · **Amends:** [ADR 0015](0015-equity-gate-owned-by-daily-screen.md),
[ADR 0014](0014-macro-fetch-desktop-only.md)

## Context

ADR 0015 moved `equity_deleveraging` to a daily cloud computation and left two items open for the
two gates that stay on the weekly desktop `macro-refresh`: `credit_stress` and
`inflation_duration_shock`. An audit of what keeping that setup costs ranked them first and second.

**1. Release streaks were stepped on the wrong clock.** `step_hard_gate` advances once per call,
and `macro-refresh` called it once per run. `release_consecutive_closes: 5` counts trading-day
closes, so this stepping had three effects:

- An active gate needed five **weeks** to release, not five sessions.
- A trigger that fired and faded between Sunday runs was never seen. Only the latest day was ever
  checked.
- Every same-day re-run advanced the streak again. The three test runs on 2026-09-11 would each
  have counted as a close.

The first two fail closed and open respectively. The third can release an active gate early.

**2. A credit shock could go unseen for up to a week.** HY OAS lives on FRED, which cloud routines
can't reach (ADR 0014), and the 2026-09-15 EODHD smoke test confirmed that no cloud-reachable
source carries it either. Between Sunday refreshes, daily-screen could keep approving new entries
while the credit gate should be active. This is the one path in the macro layer that fails open.

## Decision

### Replay every close since the last one processed

`engine.macro.credit_stress_daily` and `inflation_shock_daily` turn the fetched series into
`(date, triggered, release_met)` rows computed from each day's own inputs: a 20-observation
lookback for HY OAS, and 10 observations for the three inflation series, each measured within its
own series so a date one series skips doesn't shift the others.
`engine.macro.advance_hard_gate` steps once per row dated after a stored cursor,
`hard_gates.<gate>.last_observation_date`, and returns the new cursor. It is idempotent: a re-run
with no new data steps zero times.

A missing cursor stops the run instead of guessing. A cursor that's too early would re-count closes
the stored state already reflects, and that fails open.

**Seeding the cursor.** Both cursors were seeded on 2026-09-15 by replaying the full recent history
from an inactive start: 765 HY OAS closes (2023-10-12..2026-09-11) and 756 aligned inflation closes
(2023-09-01..2026-09-11). **Neither gate had a single trigger day in three years**, and both ended
inactive with a zero streak. The weekly-stepped states were therefore correct; no missed trigger
was hiding in the gaps.

### Daily credit early warning via a rate-hedged ETF ratio

`daily-screen` §1e computes `engine.macro.credit_proxy_check`: how far the HYG/SHY daily price ratio
sits below its high over the trailing 20 sessions. At `drawdown_pct: 1.5` or more, the Slack
notification leads with a "credit stress likely — run macro-refresh now" line.

**It is a warning, never a gate.** It changes no gate state, threshold, or verdict. §6.1 defines
the credit gate on HY OAS, and a proxy standing in for it would be an unreviewed spec change. Its
only job is to shrink the blind spot from up to a week to one session by getting a human to refresh
the real inputs.

**Why a ratio, and why SHY.** Calibrated on one year of Robinhood daily bars (2025-09-02..2026-09-11)
against FRED's HY OAS and DGS10, 20-session windows, 235 aligned sessions:

| Proxy | corr w/ HY OAS Δ | corr w/ 10Y Δ | sessions ≥ 1.5% | HY OAS Δ on those days | 2026-09-11 |
|---|---|---|---|---|---|
| HYG alone | 0.54 | 0.47 | 16 | −6..+43bp | 1.65% |
| **HYG/SHY** | **0.74** | **0.24** | **6** | **+32..+43bp** | **0.89%** |
| HYG/IEI | 0.76 | −0.40 | 5 | +16..+39bp | 0.12% |
| HYG/IEF | 0.65 | −0.62 | 24 | +12..+39bp | 0.00% |

- **Raw HYG** mixes rates with credit. On 2026-09-11 it sat 1.65% off its high on a 33bp rise in the
  10-year while HY spreads *tightened* 6bp, which is a false alarm.
- **Duration-matched hedges** (IEI, IEF) over-correct. When yields rise the hedge falls further than
  HYG, so the ratio improves. That hides stress in exactly the scenario where yields and spreads
  rise together.
- **SHY** removes most of the rate exposure while leaving a small residual that errs toward firing.
  Run through the engine function itself, it tripped on 6 sessions: 2025-10-10, then five between
  2026-03-13 and 03-30. Those were the year's two genuine widening episodes, with HY OAS up 32–43bp
  over 20 days on each of those days. None of HYG's twelve month-start ex-distribution drops (up to
  0.89%) tripped it.

Config: `tripwires.credit_proxy` (`symbol: HYG`, `hedge_symbol: SHY`, `lookback_sessions: 20`,
`drawdown_pct: 1.5`). This is a project threshold the spec never defined, so
`engine/config.example.yaml` now differs from §20 in exactly two places (this and ADR 0016's
`breadth_min_coverage`). Both are pinned in `test_config.py`.

## Consequences

- An active credit or inflation gate releases after five real closes, catches triggers between
  runs, and can't be advanced by re-runs. It is still only *evaluated* weekly, so an activation is
  recorded up to a week late. The early warning is what narrows that gap for credit.
- The inflation gate has no equivalent early warning. Its inputs are also Treasury yields, which
  EODHD's free tier serves to cloud routines with values identical to FRED (30/30 matched on
  2026-09-15). Moving it to a daily cloud computation is the natural next step, pending validation
  of a derived 5y5y breakeven against FRED's T5YIFR.
- **Calibration limits.** The sample year was calm: the largest 20-day HY OAS widening was +43bp,
  against a spec trigger of 150bp. The tripwire has never been observed in a real credit event.
  In one, a 150bp widening implies roughly a 5% move in the ratio at HYG's duration, far past the
  1.5% line, so it should fire early. That is inference, not observation, and the threshold should
  be revisited after the first genuine episode.
- Cost: one extra Robinhood call per daily-screen run.
