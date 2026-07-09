# Storage schema

Every daily run writes to the **private** data repo (`leaps-hunter-data`, see ADR 0002):

```
daily/YYYY-MM-DD.json   machine-readable run record (shape below)
daily/YYYY-MM-DD.md     human report (one of the four v6 §8 formats)
latest.json             verbatim copy of the newest daily JSON — single read for the
                        dashboard and the quick-eval skill
surfaced.json           rolling history of surfaced names (repeat-candidate guard)
```

The public repo ships the same shapes as synthetic examples in [`data-demo/`](../data-demo/).

Design rules: **file-per-day** (greppable, diffable, absence = failure signal); no
database; `schema_version` on every file so readers can evolve; **tickers only** for
anything positions-derived — never sizes, cost basis, or account identifiers; numbers
that couldn't be verified are `null` with a `note`, never estimated.

## `daily/YYYY-MM-DD.json`

| Key | Type | Notes |
|---|---|---|
| `schema_version` | int | currently `1` |
| `date` | string | trading date, `YYYY-MM-DD` |
| `run` | object | `started_at` (ISO), `mode` (`scheduled`\|`manual`), `report_type` (`ZERO_TRADE`\|`CANDIDATE`\|`DEGRADED`\|`HOLIDAY`), `framework_version` |
| `regime` | object | `verdict` (`RISK-ON`\|`NEUTRAL`\|`RISK-OFF`\|`STRESSED`), `confidence` (`High`\|`Medium`\|`Low`), `reasoning`, `indicators` (map: each `{value, trend, source, as_of, note?}` — `value: null` + `note` when unobtainable), `regime_change_challenge` (string), `effective_threshold` (int — 70 + regime bump per v6 §4d) |
| `rotation_watch` | object | `summary` (the one-liner), `direction` (`toward`\|`away`\|`unclear`), `targets` (string[]), `confidence`, `signals` (string[] of cited observables) |
| `thesis` | object | `name`, `adopted` (date), `status` (`INTACT`\|`WEAKENING`\|`BROKEN`), `challenge` (string, full text on Mondays, `null` otherwise) |
| `screened` | array | every name looked at: `{ticker, source: core\|discovery, disposition: gated\|scored\|watch, gate_failed?, score?, note}` |
| `new_name_quota` | object | `{required, met, names[]}` |
| `candidates` | array | full records for names ≥ effective threshold — see below |
| `nearest_miss` | object\|null | `{ticker, reason}` — only meaningful on zero-trade days |
| `repeat_flags` | array | `{ticker, last_surfaced, what_changed}` |
| `correlation_set` | object | `{equities: string[], options: string[]}` — **tickers only** |
| `watchlist_changes` | array | `{ticker, action: add\|drop, reason}` |
| `data_freshness` | object | per source: `{ok: bool, at: ISO\|null, note?}` for `robinhood`, `web`, `massive` |
| `degraded` | object | `{is_degraded: bool, missing: string[]}` |

### Candidate record (`candidates[]`)

```
ticker, company, score (int), tier (ELITE | HIGH CONVICTION | WATCH-ONLY),
scores: { entry_timing/25, catalyst_density/20, valuation_quality/20,
          positioning_sentiment/20, structure_survivability/15 },
entry:   { price, recent_move, why_now },
catalysts: [ {horizon: near|mid|long, text, company_controlled: bool} ],
valuation: { summary, rate_adjustment_applied: bool },
positioning: { summary, evidence[] , rotation_watch_aligned: bool },
structure: { type: deep_itm_call | itm_call | debit_spread, strike, delta,
             expiry, premium, breakeven, contracts_per_10k,
             liquidity: {oi, spread_pct, avg_volume, verified_at, source: "robinhood"} },
scenarios: { bear|base|bull: {probability, stock_price, leaps_return_pct},
             asymmetry_ratio, weighted_ev_pct },
risk:     { invalidation[], profit_ladder, time_exits, macro_trigger },
repeat:   null | {last_surfaced, what_changed}
```

## `surfaced.json`

```json
{ "schema_version": 1,
  "entries": [ { "ticker": "...", "date": "YYYY-MM-DD", "score": 0, "tier": "..." } ] }
```

Append-only; the repeat-candidate guard (v6 §3c) queries the last 10 trading days.

## Reader contracts

- **Dashboard:** renders entirely from `latest.json` + `daily/*.json`; shows a STALE
  banner whenever `latest.json.date` ≠ the current trading day.
- **Quick-eval skill:** trusts `latest.json` only if dated today (trading day);
  otherwise labels its output STALE CONTEXT and reuses nothing per-ticker.
- **Missing file for a trading day = the run failed.** Holidays produce HOLIDAY files,
  so absence is never ambiguous.
