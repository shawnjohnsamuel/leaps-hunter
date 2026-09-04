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
| VIX, SPX | `fetch_fred_series("VIXCLS")`, `("SP500")` | §6.1 equity-deleveraging gate |
| Breadth | `state/macro-latest.json`'s `breadth` block | Desktop-cadence job, separate from this one (ADR 0012) |

Compute each §6.1 gate's trigger/release booleans, call `engine.macro.step_hard_gate` against
the prior state in `state/macro-latest.json`, and compute `engine.macro.compute_restricted_regime`
for `R`. Write the full result back to `state/macro-latest.json` with `run_type: "macro_refresh"`.

### 2. NTM estimate-revision refresh (§10 patterns 2 & 3)

For every name in `state/watchlist.json` (active or not — refreshing a dormant name's NTM is
cheap and keeps `weekly-review`'s cloud run from ever needing this data mid-week), call
`engine.sources.fetch_av_earnings_estimates` then `compute_ntm_eps_revision`, paced ≥1.2 seconds
apart (Alpha Vantage throttles aggressively — confirmed empirically). Store the resulting
`NTMResult` (or its `reason` if unavailable) in each entry's `ntm` field.

### 3. Commit and push

`git add -A && git commit -m "macro-refresh YYYY-MM-DD: <one-line summary>" && git push` in the
data repo. Use the same commit-message discipline as every other skill in this project — explain
what changed and why a number moved, not just which files changed.

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
