# Phase 0 findings — capability verification

**Run:** 2026-09-03 · **Status:** complete · **Plan:** [v7-migration-plan.md](v7-migration-plan.md)

Phase 0 exists to test the assumptions the v7 build rests on, rather than inherit them from
the v6 build notes. Four passed, three gaps were confirmed, and one new defect was found that
would have been invisible in production.

## Cloud execution — PASS

A throwaway one-time routine (`trig_01JHN2EnT63H2GiQQandCWZ5`, since disabled) ran in
Anthropic's cloud with no laptop involved and returned:

```
SMOKE PASS | accounts=5 | nav_field=present | equity_positions=0 | option_positions=0
          | massive=absent | rh_historicals=present | rh_chains=present | note=none
```

- **Connectors auto-attach.** The routine was created without specifying `mcp_connections`
  and the server populated the account's connectors anyway — Robinhood among them, at
  `agent.robinhood.com/mcp/trading`. No manual wiring step is needed. This validates
  ADR 0008 and retires ADR 0005's laptop dependency.
- **NAV is reachable from the cloud** — v7 §0's hard precondition is satisfiable there.
- `get_equity_historicals` and `get_option_chains` are both present in the cloud tool set.

Note for later phases: **the run transcript contains raw tool results**, including account
identifiers returned by `get_accounts`. Prompt-level privacy rules constrain what the agent
*writes*, not what the platform logs. The privacy boundary that matters is therefore still the
sanitizer allowlist and what gets committed to the repos — not the routine prompt.

## DEFECT — multi-account NAV selection

**Severity: high. Fails silently as a normal `NO TRADE`.**

`get_accounts` returned **5 accounts**. `get_portfolio` requires an `account_number`, and the
smoke-test agent picked one on its own — landing on an account whose `total_value` is `0`, with
zero equity and zero option positions.

Under v7 that is not a harmless mistake. NAV flows straight into §13.3
(`N_max = floor(f_trade × NAV / (100 × P0_entry))`), so **NAV = 0 makes `N_max = 0` for every
candidate at every structure.** The system would emit `NO TRADE` on every name, every day,
with a correct-looking rationale — and zero-trade days are the *expected* output, so nothing
would ever look wrong.

**Required design change (Phase 2/4):**

- The account is **configured, not inferred**. `state/config.yaml` carries an explicit
  `portfolio.account_ref`; the engine never picks an account heuristically, and never falls
  back to "the first one" or "the default one" without that reference matching.
- The engine **hard-fails on a zero or missing NAV** with `NO TRADE — DATA INSUFFICIENT`
  naming NAV as the missing input (v7 §18 requires naming it), rather than proceeding to
  produce arithmetic rejections that look like ordinary discipline.
- Position inventory is read from the same configured account, so §15's portfolio tests and
  §14's `f_issuer` / `f_mechanism` caps cannot silently evaluate against an empty book.

## Data sources — what works

| Source | Result | Notes |
|---|---|---|
| **Robinhood option quotes** | **PASS — §12 fully implementable** | See field inventory below |
| **FRED, keyless CSV** | **PASS** | All 9 required series returned; see truncation caveat |
| **Massive — grouped daily** | **PASS (desktop only)** | 12,541 tickers in one call; 11,602 for a date ~200 sessions back. Breadth is computable. |
| **Massive — short interest** | **PASS (desktop only)** | FINRA bi-weekly; feeds §11 positioning |
| **Massive — Treasury yields** | **PASS (desktop only)** | Daily to 1962 |
| **Massive — live option chains** | **FAIL — 403** | ADR 0004 holds; Robinhood remains sole live-chain source |
| **Massive — Benzinga (Partners)** | **FAIL — 403** | Earnings estimates, ratings, consensus all gated |
| **Massive — in cloud routines** | **ABSENT** | Not a claude.ai connector; cannot attach to a routine |

### Robinhood option quote — field inventory

One live quote (CRM Jan-2028 $230 call, 2026-09-03) returned every input §12 needs:

| §12 requirement | Field | Value |
|---|---|---|
| Executable entry (§12.2) | `ask_price` / `bid_price` | 78.95 / 75.60 |
| Quoted spread ≤6% (§12.1) | derived | **4.34% — passes** |
| Open interest ≥500 (§12.1) | `open_interest` | **720 — passes** |
| Quote age ≤60s (§12.1) | `updated_at` | ISO timestamp, computable |
| Strike-specific IV (§12.1, §12.3) | `implied_volatility` | 0.4374 |
| Exposure vector (§15) | `delta` `gamma` `vega` `theta` `rho` | 0.7431 / 0.00235 / 1.0095 / −0.0574 / 1.668 |
| DTE 365–900 (§12.1) | derived | 505 days — passes |
| Depth for the fill test | `bid_size` / `ask_size` | 279 / 134 |

`high_fill_rate_buy_price` / `low_fill_rate_buy_price` are a partial stand-in for §12.1's
30-minute marketable-limit test, which has no read-only implementation. Modelled, flagged
`[ASSUMPTION]`, and revisited against real fills under §17.7.

**This live quote also validates the plan's feasibility arithmetic.** Executable entry
`P0 = 78.95 + 0.25 × 3.35 = 79.79` → **$7,979 per contract** → minimum NAV at the §17
unvalidated 0.25% cap of **$3.19M**, against the plan's $3.2M estimate. The
[migration plan §3](v7-migration-plan.md) table stands as written.

Separately: CRM lists expirations through **2028-12-15**, giving four inside the 365–900 day
window. v7's DTE band is materially less binding than v6 §6.5's duration floor, which killed
TRI (7/10) and CSGP (8/12) for reasons unrelated to merit.

## Confirmed gaps and their rulings

**1. NTM estimate revisions — no source.** Benzinga is a paid tier; Robinhood's
`get_equity_fundamentals` carries valuation and profile data but no analyst estimates; SEC
facts are actuals. §10's quiet-inflection (≥+5%/60d) and breakout (≥+10%/60d) patterns are
therefore **unimplementable on the current stack**. Ruling required — three options:
   - Upgrade the Massive plan to reach Benzinga (cost, and still desktop-only)
   - Add a separate estimates provider as a claude.ai connector so it also reaches routines
   - Ship with **patterns 1 (panic) and 4 (bottleneck expansion) only**, marking 2 and 3
     `UNAVAILABLE — no estimate source`, per §3's rule that an unavailable required metric
     makes the affected class ineligible rather than passing it

**2. Massive is absent from cloud routines.** It is not a claude.ai connector, and Claude
Code-configured MCP servers cannot attach to routines. What actually breaks:
   - **Breadth (§6.1)** — grouped daily is the only source. Desktop-only.
   - **Historical option OHLC (§17 backtest)** — desktop-only.
   - Everything else has a Robinhood or FRED substitute: equity OHLC →
     `get_equity_historicals`; index levels → `get_index_quotes` / FRED `SP500`; yields → FRED.

   Ruling: the cloud daily path runs on **Robinhood + FRED only**. Breadth is computed on the
   desktop on a weekly cadence and committed to `state/breadth.json`, which the routine reads
   as cached state; until it exists, ADR 0012's fail-closed rule governs.

**3. FRED truncates ICE BofA series.** `fredgraph.csv` returns `BAMLH0A0HYM2` only from
2023-09-04 (795 rows) even with `cosd=1900-01-01` — roughly three years, against a true series
start of 1996. §6.2 requires percentiles "against the longest reliable published history," and
a 20th-percentile HY OAS computed on three years is not that. The other eight series returned
full history (`DGS10` to 1962, `VIXCLS` to 1990, `DFII10` to 2003; `DFII30`'s 2010 start is the
real series start, not truncation). Ruling: use the keyed FRED API for ICE series, or record
the short window as an explicit `[ASSUMPTION]` under §2 with a §21 entry.

## Current macro readings (informational)

Pulled during verification, not a regime call — the §6 engine does not exist yet.

| Series | Value | Date |
|---|---|---|
| HY OAS | 2.66 | 2026-09-02 |
| 10Y nominal / real | 4.79 / 2.44 | 2026-09-01 |
| 30Y real | 2.98 | 2026-09-01 |
| 5y5y fwd breakeven | 2.33 | 2026-09-02 |
| VIX | 15.20 | 2026-09-02 |

Nothing here is near a §6.1 hard-gate trigger. HY OAS at 2.66 is historically tight, which
suggests `R` will likely carry the `hy_oas_lt_20pct` component once §6.2 is implemented — the
throttle, not the gate.

## Exit criteria

| Criterion | Status |
|---|---|
| Cloud connector access confirmed | **met** |
| NAV + positions reachable from cloud | **met** (with the account-selection defect logged) |
| Estimate-revision gap resolved or scoped | **scoped — needs a ruling** |
| Breadth gap resolved or scoped | **scoped — desktop cadence + fail-closed** |

Phase 1 is unblocked. The estimate-revision ruling is needed before Phase 2 implements §10.
