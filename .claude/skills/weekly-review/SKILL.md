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

**This skill is cloud-safe and reads macro/NTM state; it never fetches it.** FRED, Alpha
Vantage and multpl.com are unreachable from a cloud routine (ADR 0014). Since ADR 0021 the
refresh runs as a **GitHub Action in the data repo** (`.github/workflows/macro-refresh.yml`,
which runs `scripts/macro_refresh.py`), every weekday at 14:00 UTC and on Sunday at 13:30 UTC,
before this skill. It replaced the desktop scheduled task, which stalled on permission prompts
and let the state go 16 days stale in October.

A name this review *admits* has no `ntm` until the Action's next run, normally the next
weekday morning, which is before the next `daily-screen`. Nothing needs to be run by hand.

## Setup

1. Locate the private data repo's checkout directly — `find / -maxdepth 4 -iname "leaps-hunter-data" -type d` in a cloud routine (it's always a sibling checkout, one of the routine's own `sources`), or ask the user once for the local path in a desktop session. **Never write a `.local` pointer file to resolve this** — a 2026-09-04 cloud run found the harness's sensitive-file classifier flags any `.claude/*.local` write for interactive approval, and an unattended routine has no one to approve it; the run hangs before it can ever send its own failure notification. All state files below live under `<data-path>/state/`.
2. Load `state/config.yaml` via `engine.config.load_config` — this is the only place any
   threshold exists (ADR 0010). Never hardcode a number that's in this file.
3. Load `state/watchlist.json` and `state/macro-latest.json` for prior state.

## 1. Macro hard-gate status and the R throttle (§6.1, §6.2) — READ ONLY in a cloud run

**Do not attempt to fetch FRED, Shiller CAPE, or any of §6's macro series from a cloud
routine.** A 2026-09-04 diagnostic confirmed `fred.stlouisfed.org`, `www.alphavantage.co`, and
`www.multpl.com` are unreachable from this sandbox — both raw HTTP and the `WebFetch` tool
return an explicit `EGRESS_BLOCKED` error for all three hosts. This is a fixed network policy,
not a bug; see `docs/decisions/0014-macro-fetch-desktop-only.md`. That refresh is now a separate
skill, **`macro-refresh`**, run from a desktop session on its own cadence.

In this skill, just **read** `state/macro-latest.json` and judge its age with
`engine.macro.macro_staleness(last_refreshed, today, cfg)` — the top-level `last_refreshed`
field, **not `as_of`** (ADR 0018). Act on the returned `.band`:
- **`current`** — use it as-is for the regime check below.
- **`flag`** or **`stop`** — still use it (never block the whole run on this), but flag it
  prominently and near the top of your output:
  `⚠️ MACRO STATE STALE (last refreshed <date>, <n> days) — the macro-refresh GitHub Action is failing, check its runs`. This is the
  same "flag loudly, don't fabricate, don't halt" pattern `bench-check` uses. Unlike
  `daily-screen`, a `stop` band does not halt this skill: nothing here sizes or enters a
  position, and a structural review on two-week-old macro is still worth having.

`as_of` is **not** the staleness basis and never was meant to be. It is the newest data date
common to the fetched series, and WALCL publishes weekly, so a refresh that ran hours ago
still carries an `as_of` 4–6 days old. Measuring against it made this skill flag
`macro-latest.json` as stale on 2026-09-27 (`as_of` 09-16, 11 days) when the last real refresh
was 6 days old and inside every tolerance — the same false alarm ADR 0018 removed from
`daily-screen`, which this skill was simply never updated for. If `last_refreshed` is absent
(a file written before ADR 0018), fall back to `as_of` and say in the output that you did.

Read `hard_gates`, `restricted_regime.R`, `restricted_regime.score_threshold`, and
`restricted_regime.kelly_multiplier` from the file directly — do not recompute them. If any
`hard_gates.*.active` is `true`, note it for `daily-screen`'s benefit but this skill itself
takes no action on it (that's Stage B's job).

## 2. Kill-switch check per active watchlist name (§9)

For every `state/watchlist.json` entry with `status: "active"` or
`"mechanism_ok_no_current_dislocation"`, re-check its mechanism's §9 kill switch against fresh
evidence:

- **M1** — did 2+ major customers cut next-12mo capex guidance ≥10%? Has backlog growth
  decelerated across 2 consecutive reports with management confirming normalization?
- **M2** — do 2 consecutive reports show material ARR/revenue deceleration, pricing pressure,
  or AI-usage loss without a credible offset? "Material" is a number now (ADR 0021):
  `kill_switch_thresholds.M2` in config — YoY revenue or ARR growth down by at least
  `growth_decel_pp_per_report` points versus the prior report, for `consecutive_reports`
  reports in a row.

**Every name's `kill_switch` text must name its numeric thresholds** (M1's 10% capex cut and two
reports, M2's config numbers above, M3's named metric and level). §11's `invalidation_clarity`
has a minimum of 5 out of 5, and through 2026-11-03 M2 names kept scoring 4 there because their
kill switch said "material" without a number. Rewrite any entry that doesn't meet this the next
time you touch it.
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
5. **Filing/transcript evidence** — an EDGAR semantic diff showing no AI-risk escalation
   *accompanied by* adverse KPIs. **In a cloud routine, use Robinhood's `get_sec_filing_index`
   / `get_sec_filing_facts` tools, not `engine.sources.fetch_sec_company_concept`** — the
   latter calls `data.sec.gov` directly, which is blocked by the same egress policy as §1's
   macro sources (confirmed 2026-09-04). Robinhood's filing tools proxy the same XBRL facts
   through its own API and are confirmed working from a cloud routine. `fetch_sec_company_concept`
   remains fine for a desktop session.

**Non-disclosure is a failure, not a pass** — if a name doesn't disclose enough to apply an
approved proxy, it is `s8_status: "fail"` for the narrative-reversal class, not `"pending"`.

## 4. Estimate-revision refresh (§10 patterns 2 & 3) — READ ONLY in a cloud run

**Do not call Alpha Vantage from a cloud routine** — `www.alphavantage.co` is blocked by the
same egress policy as §1. The macro-refresh GitHub Action writes each name's `ntm` field. Here,
just read it and check its `as_of` (written since ADR 0021): flag prominently if it is more than
5 trading days old (§3), never re-fetch, never fabricate a revision figure.

## 5. Entry-pattern assignment (§10) and invalidation rules (§16)

For each active name, (re-)assign which of the four §10 patterns are structurally plausible —
not which currently qualify (that's `daily-screen`'s job). M1 names never get
`quiet_inflection`; M3 names never get `bottleneck_expansion` — see
`docs/storage-schema-v7.md` for the reasoning already applied to the seed watchlist.
Predefine §16's invalidation criteria, catalyst timetable, and profit/roll policy per name
**before** any entry, not after.

## 5a. Cached pattern inputs (ADR 0021)

Through 2026-11-03 only §10's panic pattern had ever cleared. The other three were never
evaluated, because their judgment inputs were never supplied, and a missing input fails
closed. Those inputs come from filings, change at most once a quarter, and belong here, not in a
daily run. For every active name, keep a `pattern_inputs` block in its `state/watchlist.json`
entry, for the patterns it is assigned:

```json
"sector_etf": "IGV",
"pattern_inputs": {
  "as_of_filing": "10-Q 2026-09-30 (filed 2026-10-28)",
  "quiet_inflection": {
    "accelerating_metrics_count": 2,
    "accelerating_metrics": ["revenue", "operating_margin"],
    "basis": "[FACT] YoY growth for each of the last three quarters, from get_sec_filing_facts"
  },
  "bottleneck_expansion": {
    "backlog_vs_revenue_growth_pts": 18.0,
    "backlog_to_revenue_stable_or_rising": true,
    "pricing_or_margin_evidence": true,
    "basis": "[FACT] RPO/backlog vs revenue YoY growth, the smaller of the last two reports"
  }
}
```

- **`accelerating_metrics_count`** counts how many of {revenue, cRPO/bookings, FCF, gross margin,
  operating margin} accelerated versus the prior two quarters (§10). Use reported YoY figures
  from Robinhood's `get_sec_filing_facts`. A metric the company doesn't disclose doesn't count.
- **`backlog_vs_revenue_growth_pts`** is backlog (or RPO, or orders) YoY growth minus revenue YoY
  growth, taken as the **smaller** of the last two reports, since §10 requires both.
  `backlog_to_revenue_stable_or_rising` compares the backlog/revenue ratio across those two
  reports. `pricing_or_margin_evidence` is true only with a dated `[FACT]`: a price increase,
  or rising gross or incremental margin.
- **`sector_etf`** is the name's sector benchmark for quiet inflection's relative-underperformance
  check (for example IGV for software, SMH for semiconductors, XLU for utilities, XLI for
  industrials, VNQ for REITs).
- **Refresh only when a new 10-Q or 10-K has been filed** since `as_of_filing`. Otherwise carry
  the block forward unchanged. That keeps this step to a few names a week, mostly during earnings
  season.
- Leave out a field you can't establish from filings rather than guessing. `daily-screen` treats
  a missing field as unresolved. Never write `option_valuation_passed`: that check is §12's, and
  runs in `daily-screen`.

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

## 7. Screener-feed candidates (ADR 0020) — read only

`daily-screen` runs the saved Legend scans (seven as of 2026-09-28) each session and records persistent hits in
`state/screener-feed.json`. This skill **reads that file and never writes it.** Don't call
`run_scan` or any other scanner tool here. The annex A exception covers `daily-screen` only.

1. Load `state/screener-feed.json`. If it doesn't exist yet, say so in the output and skip this
   section. That isn't a failure.
2. Call `engine.feed.promotable(feed, watchlist, today, cfg)` against the watchlist as it
   stands **after** §6's retirements. If `window_full` is false, report `window_sessions` and
   stop here: nothing is promotable until the window fills. If `last_session` is more than a
   few trading days old, flag that the daily feed may not be running.
3. Treat each `promotable` ticker as an **admission candidate on exactly the same path as any
   other**: a §5 mechanism with dated evidence, the §9 kill switch, §8 through Robinhood's SEC
   tools for an M3 name, §10 pattern assignment and §16 invalidation rules. §6's cap-and-replace
   applies too. There are no shortcuts: persistence in a price scan says the name is moving, not
   that it has a mechanism. Rejecting most of them is the expected outcome. Work in the order
   `promotable` returns (most hits first, multi-source first), and stop when the week's budget
   for new names is spent. Carry the rest to next week; they'll still be in the feed if they
   still qualify.
4. `multi_source` names are a review-priority flag only. A name there still needs to be in
   `promotable` to be considered for admission this week.
5. `retired_rehit` names are **not** re-admitted automatically. Mention them. Re-admitting one
   needs fresh evidence that whatever retired it no longer applies, recorded like any
   admission.

Known traps in the feed's sources:

- **T2/T4 admit deep cash burners.** XNDU showed an operating margin near −1268% on
  2026-09-23. §5's mechanism bar and §9's kill switch have to catch these. The feed doesn't.
- **T4 skews to crypto and crypto-treasury names** in risk-on tapes (BMNR, SBET, BTDR, MARA).
  Treat a cluster as one correlated bet. The 2026-09-03 bench-checks already found bitcoin
  treasuries have no §5 mechanism.
- **T5 reads same-day options flow**, about 45 minutes of it at the daily run. A single T5 hit
  is noise, which is what the persistence rule is for.
- **T3, T6 and T7 overlap on gold and silver miners** (CDE, HL, AG, SBSW in T3 and T7; GFI in T6
  and T7 on 2026-09-28). A multi-source flag from these pairs shows the metals moving together.
  It is not independent confirmation.
- **T7 is a sector sleeve.** Every hit moves with gold and silver, so treat a T7 cluster as one
  correlated position. A miner still needs a real §5 mechanism: a metal price is not one.
- **The source sets entry timing.** T1/T2 ("falling now") fit §10's panic pattern. T3/T4
  ("recovering off lows") fit breakout or quiet inflection. T5 (call flow) suggests breakout;
  T6 (cheap quality) suggests quiet inflection. Use this when assigning
  `permitted_entry_patterns`.

**On admission, record provenance** on the new watchlist entry: `"admitted_via":
"screener_feed"` and `"feed_sources": [...]`, copied from the item's `sources`. Names admitted
any other way carry no `admitted_via` field.

## 8. Paper-ledger marks (§17, ADR 0021)

`state/calibration.json` only counts toward lifting §17's 0.25%-of-NAV cap once entries close,
and before ADR 0021 nothing ever closed one. For every entry with `realized_outcome: null`
and no `duplicate_of`:

1. Look up the logged contract (`contract_expiration`, `strike`, `option_type`; older entries
   carry only the `contract` string, e.g. `"2028-01-21 $600 call"`) with `get_option_instruments`
   and `get_option_quotes`. Mark it with `engine.ledger.mark(entry, today, bid)`, the bid being
   what a paper exit would actually get. If there's no quote, mark `bid: None` with a note. Never
   estimate one.
2. Close it with `engine.ledger.close(entry, today, reason)` if `engine.ledger.due_to_close` is
   true (`reason: "horizon"`), or if this review fired the name's §9 kill switch
   (`reason: "kill_switch"`). Close at the latest priced mark. `close` refuses if there isn't
   one, and that's correct.

This skill writes only `marks` and `realized_outcome` in that file. `daily-screen` appends the
entries.

## Output

Write `weekly/YYYY-MM-DD.json` (see `docs/storage-schema-v7.md`), update `state/watchlist.json`
in place (kill-switch results, §8 verdicts, pattern assignments, `pattern_inputs`,
retirements/admissions — never the `ntm` field, which only the macro-refresh Action writes),
update `state/calibration.json`'s marks (§8 above), and commit + push in the data repo:
`git add -A && git commit -m "weekly review YYYY-MM-DD: <one-line summary>" && git push`.
Do not touch `state/macro-latest.json` or `state/nyse-constituents.json` at all — `macro-refresh`
owns every key in the macro file except `hard_gates.equity_deleveraging` and `breadth`, which
`daily-screen` owns, and `macro-refresh` owns the constituents list. Never write
`state/screener-feed.json` either: `daily-screen` is its only writer (ADR 0020).

The weekly JSON gets a `screener_feed` block: `window_sessions`, `promotable` (the tickers
considered), `admitted` (ticker + mechanism), `rejected` (ticker + the rule that rejected it, e.g.
`"§5: no mechanism"`, `"§9: cash burn"`, `"cap: weaker than every current name"`), `deferred` (not
reached this week) and `retired_rehit`. In the Slack summary, add one line:
`Screener feed: <n> promotable | admitted: <tickers or none> | rejected: <n>`.

## Cost discipline

- Batch Robinhood fundamentals/earnings calls across all active names in one request where the
  tool supports it (`get_equity_fundamentals` and `get_equity_quotes` both accept multiple
  symbols).
- §8's filing review is the expensive step. Budget it only for names actually flagged M3 and
  not already cleared/failed in a prior review within the last 30 days.
- The staleness clock (§6) is what makes this scale: a full evidence refresh (news, filings,
  NTM) is only mandatory for names past `mechanism_reverified_through` or showing live
  movement. A quiet, not-yet-due name gets the cheap kill-switch check alone. As the list
  grows toward 15, this tiering is what keeps the review's cost roughly flat rather than
  linear in list size — don't refresh everything every week just because you can.
