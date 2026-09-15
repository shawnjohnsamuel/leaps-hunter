---
name: daily-screen
description: Run v7's Stage B daily entry screen against the current watchlist — hard gates, entry patterns, scoring, executable option pricing, robust Kelly sizing, portfolio risk. Use for "run the daily screen", "screen today", "daily run", "morning screen".
---

# Daily Screen (framework v7, Stage B — §4.2, §18)

Read `framework/v7.md` in full before running this. This skill is operational glue: it names
which `engine/*.py` function computes which number and in what order. **It does not discover
new names** (§4.2) — it screens exactly the watchlist Stage A produced. If a name looks
interesting but isn't in `state/watchlist.json`, note it for the next `weekly-review` and move
on; adding it here would defeat the anti-overtrading purpose of the Stage A/B split.

**The first line of every run's output is `NO TRADE` unless every gate passes for every
candidate (§18).** A `NO TRADE` day is success, not failure (§0).

## 0. Hard preconditions (§0) — stop immediately if any fails

Output `NO TRADE — DATA INSUFFICIENT`, name the missing input, and stop:

1. **Market open today?** If not, this is a non-trading day — write a one-line note to
   `daily/YYYY-MM-DD.json` and stop. (v7 doesn't define a holiday format; carrying v6's
   discipline forward here — a missing file must never be the only signal that automation
   failed — so still write *something*.)
2. **Stage A fresh?** `state/watchlist.json.last_stage_a_review` must be ≤7 calendar days old.
3. **Live chain reachable?** One `get_option_chains` call on the first active watchlist name.
4. **NAV and positions reachable, from the configured account only.** Read
   `state/config.yaml`'s `portfolio.account_ref` — if it's `null`, stop here; this is the one
   manual setup step the project requires (ADR 0013). Call `get_portfolio` and
   `get_equity_positions`/`get_option_positions` with **that exact account number**, never a
   default or an inferred one. Phase 0 found what picking wrong costs: a $0-NAV account
   produces a `NO TRADE` that looks like ordinary discipline on every single run, forever.
5. **§12.1's 60-second quote-age rule means this cannot run pre-market.** If run before the
   opening auction has settled (roughly the first 15 minutes), quotes read as artifacts in
   both directions (confirmed empirically in this project's own 2026-07-09 run). Prefer
   ~10:15 ET or later.

## 1. Macro gate check (§6.1) — portfolio-wide, run once

`state/macro-latest.json` is written by **`macro-refresh`**, a desktop-only skill — FRED, Shiller
CAPE and Alpha Vantage are egress-blocked from cloud routines (ADR 0014). Neither this skill nor
`weekly-review` can refresh the slow-moving series in it. Read the `restricted_regime` block;
never re-derive it.

**1a. Staleness check.** Compare `as_of` to today:

- **≤7 days** — current, use as-is.
- **8–14 days** — use it, but record a `macro.staleness_flag` string in today's
  `daily/YYYY-MM-DD.json` *and* lead this run's notification with
  `⚠️ MACRO STATE STALE (as_of: <date>) — run macro-refresh`. The R throttle sets
  `score_threshold`, which is the binding constraint on most near-misses, so a stale read
  silently moves every verdict. Flag it where a human will actually see it, not only in the JSON.
- **>14 days** — stop with `NO TRADE — DATA INSUFFICIENT`, naming `state/macro-latest.json` as
  the missing input. Past two weeks the regime read is no longer evidence about today; fail
  closed rather than scoring against a number nobody has verified (§0).

This mirrors §0.2's `last_stage_a_review` precondition — the two freshness clocks are symmetric
by design.

**1b. Slow-moving gates — read, don't recompute.** `hard_gates.credit_stress` and
`hard_gates.inflation_duration_shock` come from `macro-latest.json` as the last `macro-refresh`
left them. Their inputs (HY OAS, real/nominal yields, 5y5y breakevens) drift slowly enough that
a weekly read is appropriate.

**1c. Equity-deleveraging gate — compute it fresh, every run.** Unlike the other two, this
gate's inputs move *daily*, and they are reachable from a cloud routine: Robinhood's
`get_indexes` → `get_index_quotes` (VIX latest and prior close) and `get_index_historicals`
(SPX, enough daily history for a trailing 200-session mean). Assemble:

- `vix_now`, `vix_prev`
- `spx_pct_below_200dma` — **call `engine.macro.spx_pct_vs_200dma(closes)`** with SPX's daily
  closes oldest-first, latest settled close last. Never compute this yourself: the engine
  expects a *signed* value, **negative when SPX is below its average** (−11 means 11% below),
  and the parameter's name reads like a positive magnitude. The natural hand-derivation
  `(mean − close) / mean` inverts the sign, so a real 12% drawdown arrives as +12 and the gate
  silently never fires. This exact mistake was made in a manual refresh on 2026-09-10.
- `breadth_pct_above_200dma` — **computed only when needed, never read from cache** (ADR 0016).
  First call `engine.macro.breadth_needed(vix_now, vix_prev, spx_pct, gate_active, cfg)`, where
  `gate_active` is the prior `hard_gates.equity_deleveraging.active`.
  - **False** (the normal case — VIX and SPX not both escalated, gate inactive): pass `None`
    and skip the NYSE pull entirely. This is safe, not a shortcut: the trigger returns before
    reading breadth, and release is never evaluated on an inactive gate.
  - **True**: compute it fresh, this session. Read the universe from
    `state/nyse-constituents.json` (1,750 NYSE-listed common stocks). Call
    `get_equity_historicals` in batches of **10 symbols** (Robinhood's per-call cap),
    `interval: day`, `start_time` at least ~300 calendar days back so every name has 200+
    sessions. Class shares use dot format (`BRK.B`) — pass them exactly as listed. Each
    response is ~380KB and will be saved to a file; don't read it into context. Parse every
    file with `engine.sources.parse_robinhood_daily_closes`, merge into one
    `{symbol: [(date, close), ...]}` dict, and call `engine.macro.compute_breadth(closes,
    universe, cfg)`. Pass `result.pct_above_200dma` to the gate — it is `None` when coverage fell
    below `breadth_min_coverage`, which fails closed.

  Measured 2026-09-14: 175 calls, zero errors, zero throttling, ~1.5s per call, **about five
  minutes** end to end. If a batch errors, retry it once; if calls keep failing, stop pulling,
  let `compute_breadth` report low coverage, and say so in the notification — do not guess a
  number. Never substitute `breadth.last_reading` from `macro-latest.json` for a fresh value:
  a reading from a calm week would pass as healthy breadth during a crash and suppress the gate.

then call `engine.macro.equity_deleveraging_trigger` and `equity_deleveraging_release_met`, and
step the gate with `engine.macro.step_hard_gate` — passing the prior
`hard_gates.equity_deleveraging` state from `macro-latest.json` and
`macro_hard_gates.equity_deleveraging.release_consecutive_closes` from `state/config.yaml`.

**This skill owns `hard_gates.equity_deleveraging` and the `breadth` block, and writes back
those two keys only.** When breadth was computed, update `breadth.last_reading` with the
result's fields and today's date; when it was skipped, leave the block untouched. `macro-refresh`
owns every other key in the file and must not step this gate — double-stepping would corrupt
the release streak. Split-key ownership of one file is the same pattern already
used for `watchlist.json` (`macro-refresh` owns `ntm`, `weekly-review` owns the rest), and works
for the same reason: the writers touch disjoint keys.

Stepping it here also fixes a cadence error: `release_consecutive_closes` counts *trading-day
closes*, so a gate stepped once per weekly `macro-refresh` run would take five weeks to release
instead of five sessions.

**1d. Act on the result.** If any `hard_gates.*.active` is `true`: **no new long LEAPS today**,
regardless of what anything below finds. Say so plainly and stop candidate evaluation — existing
positions may still be reviewed under §16's management rules, which is a separate activity from
this screen.

**1e. Credit early warning — every run, warning only (ADR 0017).** The credit gate (1b) is only
as fresh as the last weekly `macro-refresh`, so a spread blowout mid-week would otherwise go unseen
for days. Pull daily bars for the configured `tripwires.credit_proxy.symbol` and `hedge_symbol`
(HYG and SHY) in **one** `get_equity_historicals` call, `interval: day`, with `start_time` about
45 calendar days back. Parse with `engine.sources.parse_robinhood_daily_closes` and call
`engine.macro.credit_proxy_check(credit_closes, hedge_closes, cfg)`.

- **Tripped:** lead the notification (after any FAILED/INCOMPLETE line, before the staleness line)
  with `⚠️ CREDIT STRESS LIKELY — HYG/SHY −<drawdown>% vs 20-session high. Run macro-refresh now.`
  Record `macro.credit_proxy` in the daily JSON (`tripped`, `drawdown_pct`, `as_of`).
- **Not tripped:** record it in the daily JSON; no notification line.
- **Unavailable** (fetch failed or short history): record the reason and add one plain line to the
  notification. Don't retry more than once.

**This never changes a gate, a threshold, or a verdict.** It is a prompt for a human to refresh
the real §6.1 inputs, not a substitute for them. Don't set `hard_gates.credit_stress.active`,
don't stop candidate evaluation, and don't touch the score threshold because it fired.

It's the HYG/SHY *ratio*, not HYG alone, because raw HYG also moves with Treasury yields. On
2026-09-11 raw HYG sat 1.65% off its high purely on a 33bp jump in the 10-year while HY spreads
*tightened*. That would have been a false alarm, and the ratio read 0.89%. Calibration is in ADR 0017.

## 2. Per-candidate screen — cheapest checks first (§4.2's own ordering)

For each `state/watchlist.json` entry with `status` in `{"active"}` (skip
`"mechanism_ok_no_current_dislocation"`, `"gated_binary_event"` unless its gating condition has
since cleared, and `"retired"`):

**2a. §7 pre-scoring gates** — `engine.gates.evaluate_pre_scoring_gates`. The binary-event
check needs `get_earnings_results` for that ticker (cheap, do this before any option-chain
call). A failing gate here ends this name's screen for today — do not spend option-chain
calls on a name that's already rejected.

**2b. §10 entry patterns** — for each pattern in the name's `permitted_entry_patterns`:
- `panic` → `engine.patterns.panic_pattern`, needs recent daily closes
  (`get_equity_historicals`) and an `NTMResult` (reuse the cached one in each name's `ntm` field
  in `state/watchlist.json`, written by `macro-refresh` — do not re-fetch Alpha Vantage here.
  It is egress-blocked from cloud routines anyway, and avoiding that call is exactly the token
  cost the weekly/daily split exists to avoid).
- `quiet_inflection` → `engine.patterns.quiet_inflection_pattern`, needs the `accelerating_metrics_count`
  judgment call (from the name's Stage A evidence) and the cached `NTMResult`.
- `breakout` → `engine.patterns.breakout_pattern`, needs closes and the cached `NTMResult`.
- `bottleneck_expansion` → `engine.patterns.bottleneck_expansion_pattern`, needs Stage A's
  backlog-vs-revenue evidence.

At least one assigned pattern must have `.clears == True` to proceed. If none clears, this is
the day's **nearest miss** if it came closest — record it, move to the next name.

**2c. §11 scoring** — assign the eight `engine.scoring.ScoreSheet` dimensions from the
evidence gathered so far (Stage A's mechanism/kill-switch evidence, this session's pattern
confirmation, and — for `option_implementation` specifically — a preliminary read of the
chain's liquidity, not a separate impression). Call `engine.scoring.aggregate_score` with
`effective_threshold` from step 1's macro read (`RestrictedRegimeResult.score_threshold`).
A failing sub-gate or a below-threshold total ends this name's screen for today.

## 3. §12–§15 — only for names that cleared steps 2a–2c

**3a. Pull the live chain.** `get_option_chains` → `get_option_instruments` (DTE 365–900,
call, near the target delta) → `get_option_quotes`. This is the expensive step — it's why
steps 2a–2c run first.

**3b. §12.1 liquidity vetoes.** `engine.gates.evaluate_liquidity_vetoes`. `modeled_entry_cost`
and `fair_value` stay `None` until an executable price exists (next step) — expect
`marketable_limit_fill` and `premium_vs_fair_value` to report unresolved on the first pass;
re-run them after 3c produces those values.

**3c. Executable pricing and scenarios (§12.2, §12.3).**
`engine.optmodel.executable_entry` → `evaluate_scenarios` (bear/base/bull/extreme-bull
probabilities and targets are `[ASSUMPTION]`, per §2 — label them as such in the output).
Both `passes_ev_net` and `passes_ev_to_el` must be true.

**3d. Delta policy and structure selection (§13.1, §13.2).**
`engine.optmodel.evaluate_delta_policy` against the chosen contract's live delta, the macro
state from step 1, and (if the convexity exception is being invoked) a confirmed §15 result —
never an unresolved one. If a vertical spread is being considered instead of the outright,
`engine.optmodel.evaluate_spread_rule` — remember §13.2: permitted, never mandated; don't
reach for it just because IV looks high.

**3e. Sizing (§13.3, §14).** `engine.sizing.generate_posterior_draws` (or a draw set built
from real comparable-cohort dispersion once `state/calibration.json` has enough entries) →
`robust_kelly_fraction` → `nav_caps` (reading `is_calibrated` from whether this
mechanism/structure has ≥50 entries in `state/calibration.json`) → `compute_f_trade` →
`compute_feasibility`. **If infeasible, report `min_feasible_nav` — never a bare reject.**
Log this candidate to `state/calibration.json` regardless of feasibility; that is the point of
the paper ledger (ADR 0013).

**3f. Portfolio risk (§15).** Only meaningfully binding once real positions exist —
`engine.portfolio.evaluate_portfolio_risk` against the book with and without this candidate.
With an empty book this trivially passes; say so rather than skipping the check silently.

A name that clears every step above is a `CANDIDATE`. Everything else is `NO TRADE` for that
name today, with the specific gate or threshold that stopped it recorded (§18 requires naming
it). Record each name's `mechanism` (copied straight from `state/watchlist.json`, not
re-derived) alongside its result — Phase 7's public sanitizer tags every published name by
mechanism, and re-deriving it from scratch would risk drifting from Stage A's own assignment.

Alongside the free-text reason, record a **structured** `fail_category` from this fixed
vocabulary — Phase 7's public sanitizer aggregates counts from this field, not by parsing free
text, so use it exactly rather than inventing a new label:

`s7_binary_event` · `s7_valuation_insanity` · `s7_single_variable` · `s7_catalyst_duration` ·
`s7_governance_risk` · `s10_no_pattern` · `s10_unresolved_confirmation` · `s11_subgate` ·
`s11_threshold` · `s12_liquidity` · `s12_ev` · `s13_delta_policy` · `s14_infeasible` · `cleared`

Use `s11_threshold` (not `s11_subgate`) when the total score is the binding constraint even if
a sub-gate also happens to be unmet — match what actually stopped the name from proceeding, per
§18's own "the specific gate... that stopped it" requirement.

## Output (§18, `docs/storage-schema-v7.md`)

```
DATE: <session date>
MACRO HARD GATES: <PASS / ACTIVE — which gate>
RESTRICTED REGIME: R=<0-4> — NORMAL/RESTRICTED
WATCHLIST REVIEWED: <state/watchlist.json.last_stage_a_review>
CANDIDATES EXAMINED: <n>
CANDIDATES CLEARING ALL GATES: <n>

RESULT: NO TRADE
```

For each clearing candidate, disclose everything §18's table requires — ticker/mechanism,
verified facts (dated, cited), model assumptions, macro status, §8 status where applicable,
score + sub-gates, full option structure, friction-adjusted scenarios, net EV and robust log
growth, Kelly allocation, portfolio impact before/after, and the invalidation/management plan.

Write `daily/YYYY-MM-DD.json`, update `state/calibration.json` with every §11-scoring
candidate (feasible or not), commit + push in the data repo.

## Cost discipline

- Never re-fetch what's already cached upstream: mechanism evidence and kill-switch status come
  from `weekly-review`; NTM revisions and the macro regime come from `macro-refresh`. Neither is
  this skill's to refresh. Note that these have **different owners** — a stale `ntm` field or a
  stale `macro-latest.json` is fixed by `macro-refresh` (desktop-only), *not* by `weekly-review`,
  which is egress-blocked from both sources and can only read them. Flag staleness per §1a and
  move on; waiting for `weekly-review` to fix it would wait forever.
- Gate before you spend a chain call — §7 and §10 are cheap (quotes, historicals, earnings
  dates); §12's chain pull is the expensive step per name. A name killed at 2a or 2b costs zero
  option-chain calls.
- A zero-trade day should be cheap. If this run is burning tool calls on names already gated
  out, something upstream (Stage A staleness, a wrong `permitted_entry_patterns` assignment)
  needs fixing, not brute-forcing through.
