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

Read `state/macro-latest.json` (written by the last `weekly-review` or `daily-screen` run).
If any `hard_gates.*.active` is `true`: **no new long LEAPS today**, regardless of what
anything below finds. Say so plainly and stop candidate evaluation — existing positions may
still be reviewed under §16's management rules, which is a separate activity from this screen.

If breadth is needed today (VIX and S&P conditions both already fire) and
`state/macro-latest.json`'s `breadth` block is missing or older than `stale_after_days`, treat
the equity-deleveraging gate as **ACTIVE** (ADR 0012 fail-closed) rather than re-deriving it.

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
  (`get_equity_historicals`) and an `NTMResult` (reuse Stage A's cached one from
  `state/watchlist.json` — do not re-fetch Alpha Vantage here; that is exactly the token cost
  the weekly/daily split exists to avoid).
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
it).

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

- Never re-fetch what Stage A already cached (NTM revisions, mechanism evidence, kill-switch
  status). If it's more than 7 days stale, that's `weekly-review`'s job to refresh, not this
  skill's.
- Gate before you spend a chain call — §7 and §10 are cheap (quotes, historicals, earnings
  dates); §12's chain pull is the expensive step per name. A name killed at 2a or 2b costs zero
  option-chain calls.
- A zero-trade day should be cheap. If this run is burning tool calls on names already gated
  out, something upstream (Stage A staleness, a wrong `permitted_entry_patterns` assignment)
  needs fixing, not brute-forcing through.
