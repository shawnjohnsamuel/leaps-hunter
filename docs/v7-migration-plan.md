# v7 migration plan — framework v6.1 → v7.0

**Status:** approved 2026-09-03, in progress · **Governing doc:** [`framework/v7.md`](../framework/v7.md) (lands in Phase 1)

v7 is not a spec revision. v6 was a rubric a model followed; v7 is a risk engine a model
feeds. This plan replaces the framework, moves the daily run to the cloud, and rebuilds
the parts of the codebase that assumed the old shape.

## Decisions locked (2026-09-03)

| # | Decision | Ruling |
|---|---|---|
| 1 | Feasibility layer | **No hardcoded NAV band.** Compute `min_feasible_nav` per candidate per structure and emit it in every rejection. Stage A stays price-blind; feasibility annotates via `feasible_at_current_nav`, never filters. Infeasible-but-qualifying candidates route to the paper ledger. |
| 2 | Public plane ("Take the LEAP") | **Migrate to v7.** Rewrite sanitizer/email/dashboard for the v7 shape; keep the five v6 days as a tagged archive rendered in legacy mode. |
| 3 | v6 carry-forwards | **Keep** the enumerated read-only tool contract (v6 §2) as a non-negotiable annex, and **keep** HOLIDAY / no-session files. Dropped: the "tickers only, never counts or sizes even privately" rule (v7 §18 requires contract counts and % NAV privately; the sanitizer allowlist remains the public boundary) and the narrative lessons ledger (superseded by §21 version control + the calibration record). |
| 4 | Repo topology | **Routines run in the private data repo.** Spec, engine and config are copied in by a versioned release script so each run records the engine version that produced it (§21). Public repo stays the showcase, updated by a separate sanitize step. |

---

## 1. What actually changes

Nine subsystems change identity, not parameters. Anything reading v6's output shape breaks.

| Subsystem | v6.1 | v7.0 | Consequence |
|---|---|---|---|
| Cadence | One daily run does everything | Weekly Stage A discovers; daily Stage B only screens the watchlist | Two entry points, two output families |
| Universe | A named thesis ("SaaSpocalypse") | Mechanism taxonomy M1–M4; a sector is never a thesis | Pending successor-thesis sign-off is **moot** |
| Macro | Judged verdict RISK-ON → STRESSED | Arithmetic hard gates + `R` throttle on rolling percentiles | Zero model judgment; pure code |
| Entry | Buy panic only; 52wk-high auto-reject | Four auditable patterns; high-reject retained only inside panic | Breakouts become legal under stricter tests |
| Impairment | — | §8 AI-substitution gate: GRR, cRPO, usage, pricing, EDGAR diff | New binary pre-scoring gate |
| Scoring | 5 dimensions, tiers at 70/75/85 | 8 dimensions, 5 mandatory sub-gates, 75 / 80 restricted | 88 total with 11 on Thesis Fit is a reject |
| Option math | Asymmetry ratio ≥ 3:1, prose | Executable ask-plus-slippage entry, stressed exit, IV surface, `EV/EL ≥ 0.50` | Needs a pricing model, not reasoning |
| Sizing | "contracts per $10K" | Robust fractional Kelly, 10k draws, NAV max-loss caps | Sizing becomes the system's core |
| Validity | Live from run 1 | §17: invalid until calibrated; 0.25% NAV cap until 50 observations | Paper-trading is the year-one product |

The through-line: **the model stops deciding and starts sourcing.** §6, §10, §12, §14 and §15
are arithmetic on named inputs; leaving them to prose reasoning is the single largest
correctness and token risk in the build, so they move into deterministic Python (ADR 0010).
What stays with the model is what only it can do — mapping evidence to mechanisms (§5),
judging the substitution gate (§8), scoring the four qualitative dimensions, and writing the
report with §2's `[FACT]` / `[ASSUMPTION]` / `[RULE]` labels intact.

## 2. Verified 2026-09-03, not assumed

| Result | Finding |
|---|---|
| PASS | **Cloud routines API reachable** — HTTP 200, zero routines configured. Laptop-free execution is available on this account. |
| PASS | **FRED CSV, no API key** — `BAMLH0A0HYM2` (HY OAS) pulled clean through 2026-09-02 at 2.66. Fills every macro series Massive lacks. Free, keyless, cloud-safe. |
| PASS | **Massive Treasury yields** — daily to 1962; 10Y 4.79, 30Y 5.27 as of 2026-09-01. |
| FAIL | **Massive live option chains** — 403 `NOT_AUTHORIZED` on `/v3/snapshot/options/`. [ADR 0004](decisions/0004-robinhood-sole-live-chain-source.md) holds; Robinhood remains a deliberate single point of failure. |
| FAIL | **Massive inflation expectations** — monthly only. §6.1 needs a 10-day change in 5y5y breakeven → use FRED `T5YIFR` daily. |
| OPEN | **NTM estimate revisions** — Benzinga serves ratings and price targets, not a consensus revenue/EPS revision series. §10 patterns 2 and 3 depend on it. |
| OPEN | **NYSE % above 200-DMA** — no source found. §6.1's three conditions are AND-ed, so a missing value silently disables the equity-deleveraging gate. |

Two v6-era findings survive re-testing: Robinhood is the only live chain, and off-hours
quotes are artifacts (run 2 recorded INTU Jan-2028 $220C at 3.7% on the close vs. 7.8%
intraday). Under §12.1's 60-second quote-age rule that stops being a nuisance and becomes a
scheduling constraint.

## 3. The binding constraint is arithmetic, not gates

Five production runs found five different binding gates. Under v7 none of them is what stops
a trade — §13.3 account feasibility does, before any gate is consulted.

§17 caps every position at **0.25% of NAV** until fifty comparable out-of-sample observations
exist. Day one has zero. Working backward from real Jan-2028 premiums on CRM at ~$256, ~46% IV:

| Structure | Debit / contract | Min NAV @ 1.25% (validated) | Min NAV @ 0.25% (day one) |
|---|---:|---:|---:|
| 0.75Δ outright | $8,050 | $644K | $3.2M |
| 0.65Δ outright | $6,250 | $500K | $2.5M |
| 0.55Δ outright † | $4,500 | $360K | $1.8M |
| 300/360 vertical | $2,200 | $176K | $880K |

† 0.55Δ sits below the normal-regime floor and is reachable only through §13.1's convexity
exception, which requires the full §15 variance and expected-shortfall tests to pass first.

**At current NAV, `N_max = 0` on every permitted structure including verticals.** §13.3 rejects
the outright, then rejects the spread, then rejects the trade. Paper trading is not a fallback
— it is the only output the specification permits, and it stays that way until the calibration
cohort lifts the cap.

That is not a reason to soften anything. It is why the ledger matters: **paper trades are the
calibration input that makes the engine live.** Two design rules follow, both load-bearing:

**Emit `min_feasible_nav`, never a hardcoded band.** Every rejection computes the NAV each
structure would have required and says so: `CRM 0.65Δ — rejected, requires $2.5M at
unvalidated cap / $500K post-calibration`. The log becomes a running record of what each
threshold unlocks, and rescales itself as NAV changes or calibration completes.

**Stage A stays price-blind.** Weighting the watchlist toward cheaper underlyings would let
share price influence thesis selection. §5 is explicit that price is not a mechanism, and §19
bans exactly that story-selector inversion.

## 4. Target architecture

```
TRIGGERS                    ENGINE (stdlib-only Python)        SOURCES
weekly-review  (Sun)  ──┐   engine/config.py     §20 yaml      Robinhood · chains, NAV
daily-screen   (10:15)──┼──▶ engine/macro.py      §6 gates + R  FRED · macro series
bench-check    (adhoc)──┘   engine/patterns.py   §10           Massive · OHLC, yields
                            engine/optmodel.py   §12           EDGAR + web · evidence
                            engine/sizing.py     §13.3 §14
                            engine/portfolio.py  §15
                                     │ reads + writes
                                     ▼
SHARED STATE — leaps-hunter-data (private)
  state/config.yaml   state/watchlist.json   state/macro-latest.json
  state/calibration.json (paper ledger)   weekly/   daily/   adhoc/
                                     │ manual release step
                                     ▼
PUBLIC PLANE — leaps-hunter
  scripts/sanitize.py (allowlist) ──▶ public-data/ ──▶ Take the LEAP (email + dashboard)
```

**Why Claude Code, not the alternatives.** The engine needs a Python runtime, persistent git
state, live connectors, and cron — together, in one place. A claude.ai Project has connectors
but no filesystem and no scheduler; it can read reports and discuss them, but cannot run this.
Cowork is built around plugin-and-skill workflows, not a cron'd unattended job writing to a
private git data plane. Claude Code satisfies all four; cloud routines make it laptop-free.

**The ad-hoc check reuses the daily run by construction.** `/bench-check TICKER` reads
`state/macro-latest.json` and `state/watchlist.json`, so the macro layer and every cached
mechanism, kill switch and §8 status cost zero tokens to reuse. Only ticker-specific data is
fetched, and the engine returns a compact result table rather than a reasoning trace. Two
modes, because §4.2 forbids the daily screen from discovering names:

- **On watchlist** → full Stage B pass for that one name. Can produce a trade.
- **Off watchlist** → candidacy assessment only (§5 mechanism mapping, §8 gate, §7 quality
  gates). Verdicts: `NOT A MECHANISM` / `FAILS §8` / `PROPOSE FOR STAGE A`. Cannot produce a
  trade; vocabulary stays deliberately disjoint from the daily's.

**Scheduling follows from §12.1.** A 60-second quote-age requirement plus §0's live-chain
precondition means a pre-market run outputs `NO TRADE — DATA INSUFFICIENT` every day. The
daily routine fires **10:15 ET**, after the opening auction has settled spreads. Stage A runs
Sunday, when nothing it needs is live-quoted.

## 5. Build order

| Phase | Deliverable | Exit criteria |
|---|---|---|
| **0** ✅ | Verify load-bearing assumptions | **Complete 2026-09-03** — see [phase-0-findings.md](phase-0-findings.md) |
| **1** ✅ | Land the spec, settle the record | **Complete 2026-09-03** — v7.md + provenance/amendment block · CHANGELOG · ADR 0007–0013 · 0003/0005/0006 marked superseded · [annex A](annex-read-only.md) · v6 skills deleted · README banner |
| **2a** ✅ | Engine core, part 1 — config + sources | **Complete 2026-09-03** — `engine/{yaml_lite,config,sources}.py`, 28 passing tests, `engine/config.example.yaml` (byte-identical §20 extraction). End-to-end smoke reproduces R=4 through real code. |
| **2b** | Engine core, part 2 — macro, patterns, gates | `engine/{macro,patterns,gates}.py` + tests |
| **3** | Engine quant — pricing, sizing, feasibility | `engine/{optmodel,sizing,portfolio}.py` + tests · `min_feasible_nav` in every reject path |
| **4** | State plane and calibration ledger | `state/{watchlist,macro-latest,calibration}.json` · schema doc · seed watchlist re-verified per §5 |
| **5** | Three skills | `.claude/skills/{weekly-review,daily-screen,bench-check}/SKILL.md` · dry-run against a frozen fixture day |
| **6** | Cloud routines and release step | 2 routines live · `scripts/release.py` · first unattended weekly + daily observed end to end |
| **7** | Migrate the public plane | `sanitize.py` v2 + leak tests · `render_email.py` · `app/lib/data.ts` · v7 demo days · legacy-mode rendering |

**Phase 0 — complete 2026-09-03.** Cloud execution PASSES: a routine reached Robinhood with no
laptop involved, connectors auto-attached without manual wiring, and NAV is retrievable there.
Three consequences for later phases, detailed in [phase-0-findings.md](phase-0-findings.md):

- **A high-severity defect was found.** `get_accounts` returns 5 accounts and `get_portfolio`
  requires one to be named; the test agent chose an empty account. NAV = 0 makes `N_max = 0`
  for every candidate at every structure, so the system would emit a correct-looking `NO TRADE`
  on every name forever. The account must be **configured, not inferred**, and a zero or absent
  NAV must hard-fail as `NO TRADE — DATA INSUFFICIENT` rather than flow into §13.3.
- **Massive is absent from cloud routines** (not a claude.ai connector). The cloud daily path
  runs on **Robinhood + FRED only**; breadth and §17's option backtest become desktop-cadence
  jobs writing cached state the routine reads.
- **Benzinga is a paid tier (403)**, so NTM estimate revisions have no source and §10 patterns
  2 and 3 are unimplementable as specified. Needs a ruling before Phase 2.

Robinhood's option quote carries every §12 input — bid/ask, sizes, strike-specific IV, all five
Greeks, OI and quote timestamp — and a live CRM Jan-2028 quote reproduced the §3 feasibility
table to within $20/contract.

**Phase 2.** §20's YAML becomes the only place any threshold exists; the spec prose and the
code both read it, which is what makes §21's version control enforceable. Standard library
only — no numpy, so it runs identically on the laptop and in the cloud sandbox, and 10,000
Kelly draws are fast enough in pure Python. Percentiles compute against the longest available
history, never hardcoded (§6.2 is explicit).

**Phase 3.** Black-Scholes via `math.erf`; §12.2's executable entry (`A0 + 0.25(A0−B0) + F0`)
and stressed exit; §12.3 scenarios to `EV_net` and `EV/EL`; §14's Kelly over 10,000 posterior
draws with `f_robust` at the 10th percentile. §15's variance and ES tests are near-trivial
while the book is empty and become load-bearing the first time two positions coexist.

**Phase 4.** Promoted from afterthought to core infrastructure, because §17 makes it the gate
on position size. NAV is read live each run and **never written to disk in either repo** —
only `min_feasible_nav`, percentages and contract counts persist, which reveals what the
thresholds require without disclosing what the account holds.

**Phase 6.** The heartbeat rule from ADR 0005 survives the move: the notification is the signal
that the run happened, and its absence is the alarm.

## 6. Decision record

| ADR | Subject | Disposition | Reason |
|---|---|---|---|
| 0001 | Macro as veto, never points | **Holds** | §6 strengthens it into arithmetic gates plus a throttle |
| 0002 | Two-repo public/private boundary | **Holds** | The allowlist sanitizer is still the boundary mechanism |
| 0003 | Hard 60Δ floor | **Superseded → 0007** | §13.1 replaces the floor with a calibrated delta policy |
| 0004 | Robinhood sole live-chain source | **Holds** | Re-verified 2026-09-03; Massive still 403s on chains |
| 0005 | Local scheduler, not GitHub Actions | **Superseded → 0008** | Cloud routines inherit connectors without duplicating credentials |
| 0006 | Crowding counts options only | **Superseded → 0009** | §14's issuer and mechanism NAV caps replace the gate entirely |
| 0007 | Delta policy replaces the hard floor | **New** | 0.60–0.85 normal; 0.55–0.70 only through the §15 exception; below 0.55 prohibited |
| 0008 | Cloud routines; daily run at 10:15 ET | **New** | §12.1's 60-second quote age forbids a pre-market run |
| 0009 | NAV risk caps replace correlation gating | **New** | Concentration becomes a computed constraint, not a categorical reject |
| 0010 | Deterministic engine for §6/§10/§12/§14/§15 | **New** | The model sources evidence; code decides |
| 0011 | FRED is the macro series of record | **New** | Keyless CSV covers every series Massive lacks or serves too coarsely |
| 0012 | Breadth proxy, fail-closed | **Amends spec** | Unknown breadth must not silently disable a systemic-risk gate |
| 0013 | Paper ledger is the year-one output | **New** | Stage A stays price-blind; feasibility annotates, never filters |

## 7. Open items

**All three Phase 0 gaps are now closed** — see [data-sources.md](data-sources.md) for the
verification record. Summary of the resolutions:

**Estimate revisions — SOLVED.** Alpha Vantage's `EARNINGS_ESTIMATES` serves
`eps_estimate_average_60_days_ago` alongside the current consensus, which is §10's baseline
delivered directly. Both quiet-inflection (≥+5%/60d) and breakout (≥+10%/60d) become a
one-line computation with **no 60-day self-recording wait**, so both patterns ship in Phase 2.
Free key required; belongs to weekly Stage A because of rate limits. Supersedes the
degrade-and-recover plan and removes the need for the Benzinga tier.

**Breadth — resolved by gating rather than a new source.** §6.1's equity-deleveraging gate ANDs
three conditions and the other two (VIX ≥32 for two closes; S&P ≥10% below its 200-DMA) are
keyless from FRED and cloud-reachable. Breadth is consulted **only when both already fire**, so
the daily cloud routine evaluates the cheap pair itself and escalates to desktop-maintained
`state/breadth.json` — or ADR 0012's fail-closed rule — only in that rare state. No free
breadth API exists; the published sources are websites, not endpoints.

**§6.2 percentile history — SOLVED by splitting the two uses.** FRED caps ICE BofA series at
~3 years on every public path (a licensing limit, not a parameter error). Keep
`BAMLH0A0HYM2` for §6.1's *absolute* gate, which needs only a current level and a 20-day change;
use **`BAA10Y`** (keyless, 10,167 obs back to 1986) for §6.2's *percentile* component. Logged as
an `[ASSUMPTION]` per §2 with a §21 entry — investment-grade is defensible as a percentile
input, not as a level input.

**Also settled in Phase 0:**

- **Robinhood option Greeks and IV — confirmed present.** Live quotes carry strike-specific
  `implied_volatility` and all five Greeks, so §12.1's local-outlier test and §12.3's surface
  are implementable. Where a fitted surface is not obtainable, `σj_exit` is an explicit
  `[ASSUMPTION]` with a documented parameterization, never a silent flat-IV shortcut (§12.2).
- **The 30-minute marketable-limit test** (§12.1) has no read-only implementation. Robinhood's
  `high_fill_rate_buy_price` / `low_fill_rate_buy_price` are a partial stand-in; modelled,
  flagged as an assumption, revisited against real fills under §17.7.
- **CAPE — solved.** multpl.com exposes Shiller's full monthly series (1,867 rows to 1871).

**Remaining human actions:** a free [Alpha Vantage key](https://www.alphavantage.co/support/#api-key)
(required — unblocks two entry patterns) and, optionally, a free FRED API key. Neither goes in
`mcp_connections`; both are plain HTTPS.

**Governing principle established:** prefer a keyless or keyed HTTPS endpoint over an MCP
connector for anything on the daily path. MCP connectors do not reliably reach cloud routines
(proved by Massive); Robinhood stays on MCP only because its chain, NAV and positions have no
public HTTP equivalent.

**Also settled in Phase 0:**

- **Robinhood option Greeks and IV.** §12.1 needs strike-specific ask IV to test for local
  outliers; §12.3 needs an IV surface. If the connector returns IV but not a fittable surface,
  §12.3's `σj_exit` becomes an explicit `[ASSUMPTION]` with a documented parameterization
  rather than a silent flat-IV shortcut, which §12.2 bans.
- **The 30-minute marketable-limit test** (§12.1) has no read-only implementation — placing a
  limit order is prohibited and out of scope. It becomes a modeled check against quoted depth,
  flagged as an assumption, revisited when real fills exist to compare against under §17.7.
- **CAPE percentile** for `R` — Shiller's series is monthly and needs a fetch path. Low
  urgency: HY OAS at 2.66 already suggests `R` is carrying at least one component today.

---

*This document plans a rules-based research system. It is not financial advice and contains no
recommendation to buy or sell any security. Premium figures are illustrative estimates used to
size an engineering constraint, not quotes.*
