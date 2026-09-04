---
name: weekly-review
description: Run v7's Stage A weekly structural review — refresh the watchlist, macro throttle, kill switches, mechanism evidence, and entry-pattern assignments. Use for "run the weekly review", "Stage A", "weekly screen".
---

# Weekly Review (framework v7, Stage A — §4.1)

Read `framework/v7.md` in full before running this — it is the single source of every rule.
This skill is operational glue over the spec and `engine/*.py`: it names which function
computes which number and which tool retrieves which fact. It never re-derives a formula or
a threshold in prose. If anything here disagrees with `v7.md` or `state/config.yaml`, they win.

**Cadence:** weekly, before the first `daily-screen` session of the week. **Discovery happens
here, never in `daily-screen`** (§4.2) — this is the primary defense against overtrading.

## Setup

1. Resolve the private data path from `.claude/leaps-data-path.local` (create it, asking the
   user once, if missing). All state files below live under `<data-path>/state/`.
2. Load `state/config.yaml` via `engine.config.load_config` — this is the only place any
   threshold exists (ADR 0010). Never hardcode a number that's in this file.
3. Load `state/watchlist.json` and `state/macro-latest.json` for prior state.

## 1. Macro hard-gate status and the R throttle (§6.1, §6.2)

Pull fresh series and feed them straight into `engine.macro` — do not re-derive the arithmetic:

| Series | Source | Function |
|---|---|---|
| HY OAS (`BAMLH0A0HYM2`) | `engine.sources.fetch_fred_series` | §6.1 absolute credit gate |
| BAA10Y | `engine.sources.fetch_fred_series` | §6.2 percentile input (ADR 0011 — FRED caps ICE BofA at ~3y regardless of key) |
| Real/nominal 10Y, 5y5y breakeven | `fetch_fred_series("DFII10")`, `("DGS10")`, `("T5YIFR")` | §6.1 inflation-shock gate |
| DFII30 | `fetch_fred_series` | §6.2 real-30y percentile |
| WALCL, WTREGEN, RRPONTSYD | `fetch_fred_series` each | `engine.macro.net_liquidity_series` / `net_liquidity_contracting` |
| Shiller CAPE | `engine.sources.fetch_cape_series` | §6.2 CAPE percentile |
| VIX, SPX (+ 200-DMA) | `fetch_fred_series("VIXCLS")`, `("SP500")` | §6.1 equity-deleveraging gate (the two cheap conditions) |
| Breadth | `state/macro-latest.json`'s `breadth` block | Only consulted if VIX+SPX both fire (ADR 0012); if stale, treat as unknown and fail closed |

For each of the three §6.1 gates, compute today's trigger/release booleans with the matching
`engine.macro.*_trigger` / `*_release_met` function, then call `engine.macro.step_hard_gate`
with yesterday's `HardGateState` (from `state/macro-latest.json`) to get today's state. This is
a one-step transition, not a replay — see the module's own docstring for why.

Compute `engine.macro.compute_restricted_regime` for `R` and the regime-adjusted score
threshold / Kelly multiplier. **Write the full result back to `state/macro-latest.json`** —
this file only has value if every run updates it.

## 2. Kill-switch check per active watchlist name (§9)

For every `state/watchlist.json` entry with `status: "active"` or
`"mechanism_ok_no_current_dislocation"`, re-check its mechanism's §9 kill switch against fresh
evidence:

- **M1** — did 2+ major customers cut next-12mo capex guidance ≥10%? Has backlog growth
  decelerated across 2 consecutive reports with management confirming normalization?
- **M2** — do 2 consecutive reports show material ARR/revenue deceleration, pricing pressure,
  or AI-usage loss without a credible offset?
- **M3** — has system-of-record status been lost, is strategic customer migration confirmed,
  or has the "temporary" issue become persistent in bookings/retention/pricing/cash flow?

A confirmed kill switch retires the name (`status: "retired"`) — retirement is a normal, not a
failure, outcome (§4.1). Log the evidence in the entry's `evidence` array with a `[FACT]` label
and a dated source, per §2.

## 3. AI-substitution gate for M3 names (§8)

Every M3 name must clear §8 **before** it can be scored under a narrative-reversal thesis.
This has no engine module — it requires reading actual filed disclosures, which is exactly why
ADR 0010 leaves it to the model. Evaluate all five dimensions per name, each labeled `[FACT]`
or `[ASSUMPTION]` per §2:

1. **Core retention** — GRR ≥85% (or a documented equivalent proxy if undisclosed).
2. **Forward demand** — cRPO growth ≥ subscription-revenue growth − 5pp.
3. **Usage/engagement** — the proxy matching the business model (§8's mandatory correction:
   never a consumer traffic test on an enterprise workflow vendor, or vice versa).
4. **Pricing/competitive evidence** — no material concession, win-rate collapse, or confirmed
   AI-driven customer migration.
5. **Filing/transcript evidence** — an EDGAR semantic diff (`engine.sources.fetch_sec_company_concept`
   for the underlying XBRL facts) showing no AI-risk escalation *accompanied by* adverse KPIs.

**Non-disclosure is a failure, not a pass** — if a name doesn't disclose enough to apply an
approved proxy, it is `s8_status: "fail"` for the narrative-reversal class, not `"pending"`.

## 4. Estimate-revision refresh (§10 patterns 2 & 3)

Weekly cadence specifically because of Alpha Vantage's rate limit (confirmed 2026-09-03:
throttled after two rapid requests; guidance is 1 request/second). For each active name, call
`engine.sources.fetch_av_earnings_estimates` then `engine.sources.compute_ntm_eps_revision`.
Store the resulting `NTMResult` (or its `reason` if unavailable) against the watchlist entry —
`daily-screen` reads this rather than re-fetching it, which is the token-efficiency point of
splitting Stage A from Stage B in the first place.

## 5. Entry-pattern assignment (§10) and invalidation rules (§16)

For each active name, (re-)assign which of the four §10 patterns are structurally plausible —
not which currently qualify (that's `daily-screen`'s job). M1 names never get
`quiet_inflection`; M3 names never get `bottleneck_expansion` — see
`docs/storage-schema-v7.md` for the reasoning already applied to the seed watchlist.
Predefine §16's invalidation criteria, catalyst timetable, and profit/roll policy per name
**before** any entry, not after.

## 6. Retirement and universe admission

**Evidence-triggered retirement** (unchanged): retire any name whose mechanism no longer holds
— kill switch fired, or the dislocation this mechanism targets has closed (e.g. a §10 panic
candidate that has fully round-tripped).

**Staleness clock (project addition, not in v7.md itself — added 2026-09-03 because nothing
above catches a name that's merely dormant).** Every name carries
`mechanism_reverified_through: YYYY-MM-DD`, set ~75 days out whenever it gets a real evidence
pass (not a cursory kill-switch check — an actual pull of fresh news/filings/fundamentals for
that name). At each `weekly-review`, check every name's date:
- **Past due** → this review must either give it a real evidence refresh (resetting the clock
  another ~75 days) or retire it (`status: "retired"`, reason: `"stale -- not reverified"`).
  Don't let a name coast on evidence from months ago just because its kill switch never fired.
- **Not yet due** → the cheap kill-switch-only check (§2 above) is sufficient this week; no
  need to re-pull news/filings for a name that isn't due.

This is what keeps the per-name cost from scaling with list size as the watchlist grows: only
names near their staleness deadline, or showing live movement, get the expensive full refresh
any given week.

**Cap-and-replace admission (project addition, same date).** Soft target is **15 names**, not
the full 15–25 range — treat 15 as where the list should actually sit, with 25 as a hard
ceiling only, never a target to grow toward. Below 15, admit new candidates outright: each
must independently earn a §5 mechanism assignment with dated evidence, same bar as every
existing name.

**At or above 15**, admitting a new name requires **retiring the weakest-evidenced current
name** in the same pass — never just appending. "Weakest" means: thinnest/oldest dated
evidence, furthest from its `mechanism_reverified_through` deadline, or a `status` of
`"mechanism_ok_no_current_dislocation"` that has sat dormant longest. This keeps expansion
from diluting average evidence quality — the failure mode a bigger list actually risks, not
just token cost.

## Output

Write `weekly/YYYY-MM-DD.json` (see `docs/storage-schema-v7.md`), update
`state/watchlist.json` and `state/macro-latest.json` in place, and commit + push in the data
repo: `git add -A && git commit -m "weekly review YYYY-MM-DD: <one-line summary>" && git push`.

## Cost discipline

- Fetch macro series once per run, not per name — §6's gates and `R` are portfolio-wide, not
  per-candidate.
- Batch Robinhood fundamentals/earnings calls across all active names in one request where the
  tool supports it (`get_equity_fundamentals` and `get_equity_quotes` both accept multiple
  symbols).
- Alpha Vantage: one call per name, paced ≥1 second apart, this session only — never from
  `daily-screen` or `bench-check`.
- §8's filing review is the expensive step. Budget it only for names actually flagged M3 and
  not already cleared/failed in a prior review within the last 30 days.
- The staleness clock (§6) is what makes this scale: a full evidence refresh (news, filings,
  NTM) is only mandatory for names past `mechanism_reverified_through` or showing live
  movement. A quiet, not-yet-due name gets the cheap kill-switch check alone. As the list
  grows toward 15, this tiering is what keeps the review's cost roughly flat rather than
  linear in list size — don't refresh everything every week just because you can.
