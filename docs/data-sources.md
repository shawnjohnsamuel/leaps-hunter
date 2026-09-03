# Data sources — what's available, verified, and free

**Verified:** 2026-09-03 · Companion to [phase-0-findings.md](phase-0-findings.md)

Every row below was tested by calling it, not read off a docs page. This project has twice been
burned by endpoints that are *listed* but return 403 (Massive's option chains, Massive's
Benzinga tier), so "documented" is not evidence.

## Governing principle: plain HTTPS beats MCP for anything the cloud needs

Phase 0 established that MCP connectors do not reliably reach cloud routines — Massive Market
Data is absent there because it is not a claude.ai connector, and Claude Code-configured MCP
servers cannot attach to routines. A plain HTTPS API called from `Bash`/`urllib` or `WebFetch`
works identically on the desktop and in the cloud.

**Therefore: prefer a keyless or keyed HTTPS endpoint over an MCP connector for every input on
the daily path.** MCP is reserved for what only it can provide — Robinhood's live chain,
positions and NAV, which have no public HTTP equivalent.

## Source inventory

| Source | Auth | Cloud? | Verified | Binds to |
|---|---|---|---|---|
| **FRED** `fredgraph.csv` | none | yes | ✅ 9 series | §6.1 gates, §6.2 R, risk-free rate |
| **multpl.com** (Shiller CAPE) | none | yes | ✅ 1,867 monthly rows to 1871 | §6.2 `cape_gt_95pct` |
| **Alpha Vantage** `EARNINGS_ESTIMATES` | free key | yes | ✅ via public demo key | **§10 patterns 2 & 3** |
| **SEC EDGAR** XBRL `companyconcept` | none (UA required) | yes | ✅ | §8 retention/RPO, §11 fundamentals |
| **Robinhood MCP** | connector | yes | ✅ auto-attaches | live chain, Greeks, IV, OI, NAV, positions |
| **Massive** grouped daily | connector | **no** | ✅ 12.5k tickers/call | breadth (desktop cadence) |
| **Massive** short interest | connector | **no** | ✅ FINRA bi-weekly | §11 positioning |
| **Massive** option chains | connector | n/a | ❌ 403 | — (ADR 0004 holds) |
| **Massive** Benzinga tier | connector | n/a | ❌ 403 | — (superseded by Alpha Vantage) |
| **Stooq** bulk CSV | none | — | ❌ JS challenge wall | — |

## The three Phase 0 gaps — all three now have answers

### 1. NTM estimate revisions — SOLVED by Alpha Vantage

`EARNINGS_ESTIMATES` returns, per fiscal quarter and fiscal year:

```
eps_estimate_average                          13.1624
eps_estimate_average_7_days_ago               13.1749
eps_estimate_average_30_days_ago              13.0324
eps_estimate_average_60_days_ago              13.4540   <-- §10's baseline, served directly
eps_estimate_average_90_days_ago              13.4547
eps_estimate_revision_up_trailing_30_days      3.0000
eps_estimate_revision_down_trailing_30_days   16.0000
eps_estimate_analyst_count                    24.0000
revenue_estimate_average              73,198,447,680
```

This is better than the fallback the plan assumed. §10's quiet-inflection test
(`≥ +5%` over 60 days) and breakout test (`≥ +10%` over 60 days) become a direct computation —
`eps_estimate_average / eps_estimate_average_60_days_ago − 1` — with **no 60-day
self-recording wait**. Both patterns come online in Phase 2 rather than two months after launch.

NTM is constructed by summing the next four *fiscal quarter* records and doing the same on the
`_60_days_ago` column, so the revision is measured on a true next-twelve-months basis rather
than a fiscal-year one. `eps_estimate_analyst_count` supports §2's `[FACT]` labeling
requirement (named, counted, dated).

Two caveats to encode: revenue estimates carry **no** `_60_days_ago` field, so the 60-day
revision must run on EPS — §10 permits this ("revenue **or** EPS" for quiet inflection,
"FCF/EPS" for breakout). And the free tier is rate-limited, so this belongs to **weekly Stage A**
(15–25 names, once a week), never the daily screen. Confirm current limits at signup.

### 2. Breadth — resolved by gating, not by a new source

No free API publishes % of stocks above the 200-DMA; the available sources
([thetrading.tools](https://www.thetrading.tools/market-breadth),
[breadth.app](https://breadth.app/), [MacroMicro](https://en.macromicro.me/charts/86974/Market-Breadth-Stocks-above-200-Day-moving-Average),
[TradingTwoHundred](https://tradingtwohundred.com/)) are websites, not endpoints.

But §6.1's equity-deleveraging gate ANDs three conditions, and the **other two are keyless and
cloud-reachable from FRED**:

```
SP500 7,666.60 (2026-09-02) vs 200-DMA 7,131.47  ->  +7.50%   (needs <= -10%)   FALSE
VIX last two closes [16.34, 15.20]               ->  (needs >= 32 both)         FALSE
```

Breadth is therefore only ever **consulted when the first two already fire** — a rare,
high-stress state. The daily cloud routine evaluates the two cheap conditions itself; only on a
double-TRUE does it need breadth, at which point it reads the desktop-maintained
`state/breadth.json` (from Massive grouped daily) or, if that is stale, applies ADR 0012's
fail-closed rule and treats the gate as ACTIVE. The cloud/desktop split stops mattering in
practice.

### 3. §6.2 percentile history — SOLVED by a long-history proxy

FRED caps ICE BofA series at ~3 years on every public download path (`cosd=1996-12-31` still
starts 2023-09-04; the `.txt` feed returns HTML). That is an ICE licensing limit, not a
parameter mistake, and 787 observations cannot support a 20th-percentile claim.

Split the two uses:

- **§6.1 absolute credit gate** (HY OAS ≥ 550bp, or ≥150bp widening over 20 days while above
  450bp) needs only the current level and a 20-day change. **Three years is ample** — keep
  `BAMLH0A0HYM2`.
- **§6.2 percentile component** needs a long distribution. Use **`BAA10Y`** (Moody's Baa
  corporate minus 10Y Treasury), keyless, **10,167 observations back to 1986**.

Record the substitution as an `[ASSUMPTION]` under §2 with a §21 entry: BAA10Y is
investment-grade and sits at a different level than a high-yield OAS, so it is defensible as a
*percentile* input and not as a level input. That distinction is exactly why the two uses split.

## §6.2 `R` preview

Computed from the sources above to prove all four components are sourceable. **This is a
plumbing test, not a regime call** — the §6 engine does not exist yet, and no screen has run.

| Component | Reading | Percentile | Fires |
|---|---:|---:|---|
| CAPE > 95th | 41.93 | 99.1th (1,867 mo) | **yes** |
| Credit spread < 20th | 1.58 | 10.5th (10,167 obs) | **yes** |
| 30Y real yield > 90th | 2.98 | 99.7th (4,136 obs) | **yes** |
| Net liquidity contracting | $5.779T vs $5.872T 13wk ago | — | **yes** |

**R = 4.** If the engine existed today it would read RESTRICTED: threshold 75 → 80, Kelly
multiplier 0.25 → 0.125 × `f_robust`, deltas narrowed to 0.70–0.85, and broad-beta,
unpriced-capex and pure multiple-expansion trades prohibited.

**Honest caveat on component 3.** `DFII30` begins 2010-02-22 because 30-year TIPS were only
reintroduced then — that is the real series start, not truncation. But the 2010–2026 window is
almost entirely a low-real-yield era, so "99.7th percentile" means *highest in the TIPS era*,
not *highest in history*. §6.2 asks for "the longest reliable published history," and for this
series that is genuinely 16 years. Flag it in the report rather than letting the number imply
more than it supports.

## Actions required (both free, both need a human — accounts cannot be created by the agent)

1. **Alpha Vantage API key** — <https://www.alphavantage.co/support/#api-key>. Unblocks §10
   patterns 2 and 3. Store outside the repo, alongside the existing gitignored `.local` files.
2. **FRED API key** *(optional)* — <https://fredaccount.stlouisfed.org/apikeys>. Only needed if
   full ICE BofA history is wanted instead of the `BAA10Y` proxy; the proxy is sufficient.

Neither key belongs in `mcp_connections`. Both are plain HTTPS and reach the cloud routine as
environment variables or a mounted secret.

---

*Verification record for a rules-based research system. Values quoted are source readings on
the dates shown, not recommendations.*
