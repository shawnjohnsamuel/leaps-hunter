# ADR 0020: Screener feed as a candidate source

**Status:** accepted (2026-09-24), amended 2026-09-28 (seven sources, see below) · **Amends:** [annex A](../annex-read-only.md) (one narrow
exception) · **Extends:** §4.1 (Stage A discovery)

## Context

Stage A has no systematic way to find names. Every watchlist addition so far came from §5's
seed list or from a name that happened to come up in a weekly review. Meanwhile the user built
four saved scans in Robinhood Legend that look for the price action v7's entry patterns want:
a name that is falling now, or one recovering off a deep low, and that has a liquid options
market.

The scans are a 2×2 grid. The two axes are structural, so the four rarely return the same
name: on 2026-09-23 they returned 23 hits, 22 unique tickers, and only one overlap.

|  | **Falling now** (RSI + 1-month decline) | **Recovering off lows** (deep drawdown + bounce) |
|---|---|---|
| **Quality / larger cap** | T1 Quality Dislocation | T3 Large Cap Recovery |
| **Speculative / smaller cap** | T2 Speculative Dislocation | T4 Speculative Recovery |

The quadrant matters later. A "falling now" name (T1/T2) fits §10's panic pattern and wants
entry timing now. A "recovering" name (T3/T4) fits breakout or quiet inflection and can wait
for confirmation.

A single day's hit is noise: the scans read live intraday data, RSI and 1-month change cross
their thresholds and back, and at 10:15 ET they reflect the morning print. A name that keeps
appearing is a signal worth a Stage A look.

## Decision

**1. The feed is a candidate source, never a gate.** Nothing it produces bypasses Stage A
admission (§5 mechanism, §9 kill switch, §8 via Robinhood's SEC tools, §10 pattern assignment,
cap-and-replace) or any Stage B check (§7, §10, §11, §12–§15). It never changes a verdict,
never halts a run, and never suggests a trade.

**2. `daily-screen` collects, `weekly-review` admits.** Each trading day, `daily-screen` runs
the configured scans and records which tickers hit. It never screens them, scores them or writes
`state/watchlist.json` because of them. That keeps §4.2 intact: the daily screen does not
*discover* names, because recording a scan's output is not admission. Once a week,
`weekly-review` reads the persistent hits and runs each one through its normal admission path.

**3. Persistence is counted in sessions, not calendar days.** A ticker is promotable when it hit
on at least `min_hits` of the last `window` recorded sessions (default 3 of 5) and is not
already on the watchlist. A session is a day the feed actually ran with at least one scan
answering, so holidays and fully failed runs don't count against a name. Promotion needs a full
window: nothing is promotable until `window` sessions exist. A retired watchlist name that hits
again is reported as `retired_rehit`, not re-promoted. A name hit by two or more scans within the
window is flagged `multi_source`, for higher review priority, but still needs the same count.

**4. File ownership.** `state/screener-feed.json` is written only by `daily-screen`, only
through `engine.feed.update_feed`. `weekly-review` reads it through `engine.feed.promotable` and
never writes it. It is a new file, not a new key in a shared file, so it has no split-ownership
merge risk. Scan IDs and thresholds live in `state/config.yaml` under `screener_feed`. They are
never hardcoded in a skill or a routine prompt.

**5. Fail closed per source.** A scan that errors is recorded in `last_run.sources_failed` and
named in one warning line. The other scans' hits are still recorded. A scan that returns fewer
rows than its `total_items` is recorded as `truncated` and warned on; we don't paginate. Only
tickers actually returned by `run_scan` are recorded, and every other column is ignored.

**6. A narrow exception to annex A for `run_scan`.** The annex listed `run_scan` with the scan
*writes* (`create_scan`, `update_scan_config`, `update_scan_filters`), and
`.claude/settings.json` denied it under both connector names. Git history gives no reason
specific to `run_scan`: it was grouped with the scanner tools when the deny rules were written
on 2026-09-21. `run_scan` evaluates a saved scan's filters against current market data and
returns the matching rows. It changes no scan configuration, places nothing and modifies no
account state. It is a read.

The exception is as narrow as the feature needs:

- `run_scan` is allowed only on the scan IDs in `state/config.yaml` → `screener_feed.scans`, and
  only from `daily-screen`'s screener-feed step.
- `create_scan`, `update_scan_config`, `update_scan_filters` and every other scanner write stay
  forbidden and denied. A broken or drifting scan is never repaired from a routine or a skill.
  Re-tuning is a manual edit the user makes in Legend, at most monthly.
- `settings.json` moves `run_scan` from `deny` to `allow` under both connector names. That
  permits the tool; the ID and caller restrictions are enforced by the skill and this ADR.

The user approved this exception explicitly on 2026-09-24.

**7. The Robinhood web screeners are excluded.** T3–T7 are ports of Robinhood *web* screeners.
Those have no API, and cloud routines have no browser, so only the Legend ports feed the
pipeline. (Until 2026-09-28 the T3/T4 ports used IV30 / 1-month realized volatility as a
"cheap vol" stand-in; Legend's `ivRank` field replaced it.)

## Amendment (2026-09-28): seven sources

The user added three thematic scans outside the 2×2 grid and revised T3/T4 to use Legend's real
IV Rank. Nothing in the decision above changes: the new scans are more IDs under
`screener_feed.scans`, run by the same step under the same `run_scan` exception, and the engine
has no per-source logic. Their persistence history starts on their first run; the sessions
already recorded stay valid.

| Key | Theme | Entry timing it suggests |
|---|---|---|
| T5 Cheap Call Flow | options flow, any sector: calls > 2× puts today, relative options volume > 2×, IV Rank < 30% | a catalyst someone is positioning for; breakout |
| T6 Quality at a Discount | value: P/E 1–15, ≥40% off the 52w high, ROE > 15%, IV Rank < 30% | quiet inflection |
| T7 Precious Metals Pullback | sector sleeve: PHLX Gold/Silver (XAU) members ≥30% off the 52w high, IV Rank < 30% | depends on the metal price, not the company |

Three traps come with them:

- **T5 reads same-day flow.** At 10:15 ET it has seen about 45 minutes of it, so single-day hits
  are thin and noisy. The persistence rule is what filters them. Don't lower `min_hits` for it.
- **T3, T6 and T7 overlap on miners.** On 2026-09-28 CDE, HL, AG and SBSW hit both T3 and T7,
  and GFI hit both T6 and T7. Expect multi-source flags from these pairs. In this case the flag
  shows gold and silver are moving together. It is not independent confirmation.
- **T7 is one correlated bet.** Every hit moves with gold and silver. At admission, treat a T7
  cluster as a single position.

## The seven scans (as saved 2026-09-28; documentation, not a spec)

| Key | Filters |
|---|---|
| T1 | mkt cap > $5B · RSI(14,1d) < 40 · 1-mo change < −8% · gross margin > 50% · op margin > 20% · IV30 > 35% · 30d avg options vol > 10k |
| T2 | mkt cap $1B–$25B · RSI(14,1d) < 45 · 1-mo change < −12% · gross margin > 60% · IV30 > 60% · 30d avg options vol > 10k |
| T3 | mkt cap > $5B · price / 52w high < 0.65 · price / 13w low > 1.20 · IV Rank < 25% · IV30 > 35% · 30d avg options vol > 10k · P/E 0–60 |
| T4 | mkt cap $1B–$25B · price / 52w high < 0.45 · price / 13w low > 1.20 · IV Rank < 10% · IV30 > 60% · 30d avg options vol > 20k |
| T5 | mkt cap > $2B · calls > 2× puts (today) · relative options volume > 2 · IV Rank < 30% · 30d avg options vol > 5k |
| T6 | mkt cap > $10B · P/E 1–15 · price / 52w high < 0.60 · ROE > 15% · IV Rank < 30% · 30d avg options vol > 10k |
| T7 | symbol in XAU index · P/E 1–30 · price / 52w high < 0.70 · IV Rank < 30% · 30d avg options vol > 5k |

Thresholds are tuned for roughly 3–6 hits per scan. The engine never re-implements them.

## Consequences

- Stage A gets a steady, persistence-filtered stream of names instead of relying on whatever
  comes up in a review. Promotions start once five sessions have accumulated.
- Seven `run_scan` calls add roughly 20–35k tokens to each daily run, because only tickers are
  extracted. That is far cheaper than a separate routine that would redo checkout and context
  load. If cost matters, run the feed Mon/Wed/Fri with `window: 3`, `min_hits: 2`.
- **T2 and T4 admit deep cash burners** (XNDU showed an operating margin near −1268% on
  2026-09-23). The feed doesn't filter them out; §9's kill switch and §5's mechanism bar at
  admission must.
- **T4 skews to crypto and crypto-treasury names in risk-on tapes** (BMNR, SBET, BTDR, MARA).
  Treat a cluster as one correlated bet at admission. The bitcoin-treasury bench-checks of
  2026-09-03 already found that class has no §5 mechanism.
- `changeFromCloseAllDayRatio(candlePeriod="1y")` does **not** return trailing 1-year change
  (it disagreed with Robinhood's 1Y column by 60+ points for HL). Don't build a scan on it.
- Legend expression filters (`ivRank` on a 0–1 scale, `optionsCallDayVolume`,
  `optionsPutDayVolume`, `symbol` with IN_LIST index codes, `tradeAllDay.price`, `high(...)`, `low(...)`, `atmIv30Day`,
  `statVol1Month`, `changeFromCloseAllDayRatio(...)`, `fundamental.peRatio`) can only be edited
  by re-creating the scan with `create_scan` and the full filter set, because
  `update_scan_filters` rejects expressions. That is a manual desktop operation outside this
  project's tool contract. After it, update the IDs in `state/config.yaml` if they changed.
