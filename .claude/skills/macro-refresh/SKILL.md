---
name: macro-refresh
description: Desktop-only refresh of macro hard-gate state, the R throttle, and NTM estimate revisions — the one piece of Stage A that cannot run in a cloud routine. Use for "refresh macro state", "run macro-refresh", or when weekly-review's cloud output flags stale macro/NTM data.
---

# Macro Refresh (framework v7, desktop-only — split out of weekly-review 2026-09-04)

**Why this exists as its own skill, not part of `weekly-review`:** a 2026-09-04 diagnostic
(`docs/decisions/0014-macro-fetch-desktop-only.md`) confirmed FRED, Alpha Vantage, and
multpl.com are unreachable from a cloud routine's sandbox — both raw HTTP and the `WebFetch`
tool return an explicit `EGRESS_BLOCKED` error for all three hosts. This is a fixed platform
network policy, not a bug, and not fixable from inside a routine. `weekly-review`'s cloud run
now explicitly skips this step and reads whatever this skill last wrote; **someone has to run
this skill from a desktop (or any environment with normal internet access) periodically** —
weekly is plenty, since the macro regime moves slowly and NTM estimates update at a similar
cadence to earnings, not daily.

This is the smaller, real cost of Phase 6's cloud automation: not zero laptop dependency, but
an infrequent one, confined to this one step.

## Procedure

Run this from a desktop Claude Code session with the private data repo checked out locally
(or freshly cloned).

### 1. Macro hard-gate status and R throttle (§6.1, §6.2)

Identical to `weekly-review`'s former §1 — pull fresh series and feed them into `engine.macro`:

| Series | Source | Used for |
|---|---|---|
| HY OAS (`BAMLH0A0HYM2`) | `engine.sources.fetch_fred_series` | §6.1 absolute credit gate |
| BAA10Y | `engine.sources.fetch_fred_series` | §6.2 percentile input (ADR 0011) |
| DFII10, DGS10, T5YIFR | `fetch_fred_series` each | §6.1 inflation-shock gate |
| DFII30 | `fetch_fred_series` | §6.2 real-30y percentile |
| WALCL, WTREGEN, RRPONTSYD | `fetch_fred_series` each | `engine.macro.net_liquidity_series` |
| Shiller CAPE | `engine.sources.fetch_cape_series` | §6.2 CAPE percentile |

Advance **`credit_stress` and `inflation_duration_shock` only**, one trading-day close at a time
(ADR 0017) — never once per run:

1. Build each gate's per-day conditions from the full fetched series:
   `engine.macro.credit_stress_daily(BAMLH0A0HYM2, cfg)` and
   `engine.macro.inflation_shock_daily(DFII10, DGS10, T5YIFR, cfg)`. Each row is
   `(date, triggered, release_met)` computed from *that day's* inputs.
2. Call `engine.macro.advance_hard_gate(prev_state, rows, after=gate.last_observation_date,
   release_streak_required=...)`, with the prior `active` / `consecutive_release_days` from
   `state/macro-latest.json` and `release_consecutive_closes` from config. It steps once for every
   close after the cursor and returns `(state, new_cursor, steps)`.
3. Write back `active`, `consecutive_release_days`, and `last_observation_date = new_cursor`, and
   record `steps` in the note. **Zero steps is normal** on a same-day re-run and means nothing
   new was published. Never step again to "refresh" it.

Why this matters: stepping once per weekly run made a five-close release take five weeks,
let a trigger that fired and faded between Sundays go unseen, and advanced the streak again on
every same-day re-run (three test runs on 2026-09-11 would each have counted a "close").

**If `last_observation_date` is missing, stop and report it — do not guess a start date.** A
cursor that's too early double-counts closes already reflected in the stored state, which can
release an active gate early. That fails open.

Then compute `engine.macro.compute_restricted_regime` for `R`. Write the result back to
`state/macro-latest.json` with `run_type: "macro_refresh"`.

**Do not compute or step `hard_gates.equity_deleveraging` — `daily-screen` owns that key.**
That gate's inputs (VIX, SPX vs its 200dma) move daily and, unlike everything else in this table,
are reachable from a cloud routine via Robinhood's index tools, so `daily-screen` now computes and
steps it every session. Two writers stepping the same gate would double-advance its release
streak. This also fixes a cadence error: `release_consecutive_closes` counts *trading-day closes*,
and a gate stepped once per weekly run of this skill would have taken five weeks to release
instead of five sessions.

Leave the `hard_gates.equity_deleveraging` **and `breadth`** blocks exactly as you found them —
`daily-screen` owns both (ADRs 0015, 0016) — and preserve every other key you did not compute
rather than rewriting the file wholesale.

### 1a. Source freshness (ADR 0018)

Collect the latest observation date of every series you fetched (FRED ids plus `CAPE`) and call
`engine.macro.stale_sources(latest_by_series, today, cfg)`. It judges each series against its own
publication cadence, so a weekly WALCL print being 5 days old is fine while a daily series 10 days
behind is not.

Every `engine.sources` series — `fetch_fred_series` and `fetch_cape_series` alike — is
`(ISO date, value)` oldest first, so the latest observation date is `series[-1][0]` in all of
them. Pass those straight in. **Do not convert a date in a scratch script**: `fetch_cape_series`
normalised multpl.com's display order and format on 2026-09-21 precisely so this step stops
re-deriving it, and a hand conversion is how a wrong date reaches `stale_sources` unnoticed.

Record the result in `macro-latest.json` and report it. Anything in `.stale` means a source has
gone quiet and the values derived from it can't be trusted just because this run is recent —
say so prominently rather than writing a clean-looking file. Anything in `.unconfigured` means a
series has no cadence entry in config: add one rather than letting it go unchecked.

### 1b. NYSE breadth universe refresh

`daily-screen` computes breadth over `state/nyse-constituents.json`, but it can't rebuild that
list itself: the membership source is Massive, which is a desktop extension that cloud routines
can't attach. Refresh it here, weekly. Page through Massive's `/v3/reference/tickers` with
`type=CS`, `market=stocks`, `exchange=XNYS`, `active=true`, `limit=1000`, following the cursor
until no next page is returned. Rewrite the file's `tickers`, `count` and `as_of`, keeping the
rest of its fields. Keep the list mechanical — no hand filtering.

Sanity-check before writing: the 2026-09-14 baseline was **1,750** names. If the new count
differs by more than ~5%, don't write it; report the difference instead. A sudden drop is far more
likely to mean a truncated page or an API change than 90 real delistings in a week. Normal churn is
a handful of names. If Massive is unreachable, leave the existing file as it is and say so;
membership moves slowly, so a list that's a few weeks old barely changes the breadth reading.

**Always run this step; never skip it because the list "looks fresh."** It is two or three Massive
calls. Skipping it also skips the sanity check, and it is the only step that exercises the Massive
tools — a run on 2026-09-14 skipped it as a same-day judgment call, which meant the tool approval
an unattended run depends on was never granted. Re-fetching a list that turns out unchanged is the
cheap outcome; silently not checking is the expensive one.

### 2. NTM estimate-revision refresh (§10 patterns 2 & 3)

For every name in `state/watchlist.json` (active or not — refreshing a dormant name's NTM is
cheap and keeps `weekly-review`'s cloud run from ever needing this data mid-week), call
`engine.sources.fetch_av_earnings_estimates` then `compute_ntm_eps_revision`, paced ≥1.2 seconds
apart (Alpha Vantage throttles aggressively — confirmed empirically). Store the resulting
`NTMResult` (or its `reason` if unavailable) in each entry's `ntm` field.

### 3. Write, commit and push

Set two dates in `macro-latest.json`, and keep them distinct (ADR 0018):

- **`last_refreshed`** — today, the date this run actually fetched. `daily-screen`'s staleness
  bands measure from this. Write it on every run that completed step 1, including one where
  nothing moved: "nothing changed" is still a refresh.
- **`as_of`** — the most recent data date common to the fetched series. Informational, and
  legitimately several days behind `last_refreshed` because WALCL is weekly. Never use it as the
  staleness basis.

Then `git add -A && git commit -m "macro-refresh YYYY-MM-DD: <one-line summary>" && git push` in
the data repo. Use the same commit-message discipline as every other skill in this project —
explain what changed and why a number moved, not just which files changed.

## What stays in `weekly-review` (cloud-compatible)

Everything else: kill-switch checks (Robinhood MCP + web search, both confirmed working from
cloud routines), the §8 AI-substitution gate (Robinhood's SEC filing tools, confirmed working —
they proxy EDGAR through Robinhood's own API rather than a direct `data.sec.gov` call), entry-
pattern assignment, staleness-clock enforcement, and retirement/admission. `weekly-review`
checks this skill's last `as_of` date and flags prominently (not silently) if it's gone stale,
but never attempts the fetch itself.

## Cadence

Run this whenever convenient, at least weekly, ideally right before (or same-day as) the next
`weekly-review` cloud run so its kill-switch/S8 work has fresh NTM context. There is no harm in
running it more often — Alpha Vantage's rate limit is the only real constraint, and it's paced
within this skill already.
