# ADR 0016: NYSE breadth, computed on demand in `daily-screen` via Robinhood

**Status:** accepted (2026-09-14) · **Amends:** [ADR 0012](0012-breadth-escalation-and-fail-closed.md),
[ADR 0015](0015-equity-gate-owned-by-daily-screen.md)

## Context

§6.1's equity-deleveraging gate ANDs VIX ≥ 32 for two closes, the S&P ≥ 10% below its 200-DMA,
and **NYSE breadth** < 35% above its 200-DMA; it releases after five closes with VIX < 25 and
breadth > 45%. ADR 0012 made missing breadth fail closed on both sides, and planned to compute it
on the desktop from Massive's grouped-daily endpoint over **all US common stocks**, recorded as an
assumption that deviated from the spec's NYSE wording.

That computation was never built. `breadth.pct_above_200dma` sat at `null` from the day the file
was created. On its own that looked harmless, but the fail-closed rule turns it into a trap:

- **Trigger:** missing breadth → gate fires. Conservative, acceptable.
- **Release:** `equity_deleveraging_release_met` returns `False` outright on missing breadth. An
  active gate could **never release**.

So the first genuine stress event would have halted new entries indefinitely, until someone
noticed and populated breadth by hand. The gate fails closed on the way in and has no exit.

Three constraints shaped the fix, all verified 2026-09-14:

1. **Massive can't reach the cloud routine.** It is installed as a desktop extension
   (`kind: desktop`), not a claude.ai connector, and isn't in the connector registry at all.
   Cloud routines can only attach claude.ai connectors.
2. **Massive can't define the S&P 500 on this plan.** ETF constituents returns
   `403 — not entitled`. Its ticker reference *can* list NYSE-listed common stocks: 1,750 names.
3. **Robinhood can do the whole computation from the cloud.** `get_equity_historicals` caps at
   10 symbols per call but returns 225 real daily bars per symbol from one request, uses the same
   dot class-share format as Massive (`BRK.B`), and reports unknown symbols in an explicit
   `not_found` array.

An S&P 500 universe was briefly chosen on the claim that the 35/45 thresholds are "conventionally
quoted on S&P 500 breadth." That was wrong for this spec, which says NYSE, and was corrected
before any code shipped.

## Decision

**Universe: NYSE-listed common stocks, per §6.1 as written.** Stored in
`state/nyse-constituents.json` (1,750 names), defined mechanically from Massive's reference
tickers (`type=CS`, `exchange=XNYS`, `active=true`) with no hand filtering. This removes ADR
0012's all-US-stocks deviation instead of adding a new one. It is still an approximation of the
NYSE Composite, which also includes ADRs; that gap is documented here rather than hidden.
`macro-refresh` rebuilds the list weekly on the desktop, where Massive works, and refuses to
write a count that moved more than ~5%.

**Computation: on demand, same session, in `daily-screen`.** The engine only reads breadth in two
states: when VIX and SPX are both already escalated (trigger), or while the gate is already
active (release). `engine.macro.breadth_needed` encodes exactly that, reusing
`equity_deleveraging_escalated` so the skip condition can never drift from the trigger's own
logic. On any other session breadth is passed as `None` with zero API calls — which changes no
outcome, because the trigger returns before reading it and release is never evaluated on an
inactive gate. On the sessions where it is needed, it is pulled fresh (~175 calls) and computed
by `engine.macro.compute_breadth`. **A cached reading is never used for a gate decision:** a
reading from a calm week would pass as healthy breadth during a crash and suppress the trigger —
failing open, the one direction this gate must not fail.

This retires `breadth.stale_after_days`. A value computed in the same session can't be stale, and
the old 3-day rule was unsatisfiable anyway against a weekly desktop owner.

**New threshold: `breadth_min_coverage: 0.90`.** If fewer than 90% of the universe returns a bar
on the reference date, `compute_breadth` returns `None` and the gate fails closed rather than
computing over a partial universe. It lives in `state/config.yaml` and `engine/config.example.yaml`
(ADR 0010: thresholds are config, never literals). `framework/v7.md` stays verbatim, so the
template now differs from §20 by exactly this one key; `engine/config.py` documents it and
`test_config.py` pins it so a future re-extraction can't silently drop it.

**Two data-quality guards in `compute_breadth`:**

- *Mixed session dates.* The reference date is the most common latest-bar date. Symbols ending
  on another date are treated as missing rather than blended in — a lagging feed would otherwise
  mix two sessions into one number (a full-session stall in Robinhood's daily bars was observed 2026-09-08).
- *Short history.* A listing with fewer than 200 closes can't have a 200-DMA. It is excluded and
  counted in `names_short_history` without reducing coverage, since it isn't a retrieval failure.

## Rate-limit verification (2026-09-14)

The full production workload was run from the desktop Robinhood connector before adoption:

| Measure | Result |
|---|---|
| Calls / symbols | 175 / 1,750 |
| Error payloads | 0 |
| `not_found` | 0 |
| Symbols returned with bars | 1,750 |
| Median gap between calls | 1.50s |
| Max gap *within* a wave | 2.51s |
| Wall time | 303s (every gap > 3s fell on a batch-dispatch boundary, not inside a wave) |

No throttling signature: no errors, no backoff, no latency creep from the first wave to the last.
The cloud routine uses the same claude.ai Robinhood connector, so account-level limits should
match — but the cloud sandbox path itself was not exercised, which is why the skill specifies a
single retry per failed batch and falls back to reporting low coverage rather than guessing.

**First reading:** 52.4% of 1,663 computable NYSE names above their 200-DMA as of the 2026-09-11
close (coverage 99.0%; 18 names' latest bar predated the reference date, consistent with no trade
that session in thinly traded names; 69 had under 200 sessions of history). Comfortably above both
the 35% trigger and 45% release lines, consistent with a narrow, large-cap-led tape (SPX +7% over
its own 200-DMA).

## Consequences

- The release deadlock is closed: an active gate gets a fresh breadth reading every session and
  can release on the trading-day cadence ADR 0015 established.
- A normal session costs nothing extra. A stress session — escalated, or the gate already
  active — adds roughly five minutes and ~66 MB of transient responses, parsed from disk, never
  read into model context.
- Breadth has an owner, a universe that matches the spec, and a tested computation path for the
  first time since ADR 0012 was written.
- Open: the NYSE-vs-NYSE-Composite gap (ADRs excluded) is small but real. If a backtest against a
  published NYSE breadth series ever becomes available, it should confirm the 35/45 thresholds
  behave as intended on this approximation.
