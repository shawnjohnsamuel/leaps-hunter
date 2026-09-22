# Input file — schema and where each field comes from

One JSON file per ticker. `engine/vehicle.py` reads it as is. An unknown key is an error, so a typo
fails loudly instead of being silently ignored. Every value you couldn't establish is `null`.

## Contents
- Full example
- Field sources: context, name (stocks), name (ETFs), market, dates, contracts
- The `technicals` helper

## Full example

```json
{
  "ticker": "MDB",
  "instrument_type": "stock",
  "context": {"quotes_live": true, "option_level": "option_level_2", "leverage_mode": false},
  "name": {
    "avg_daily_dollar_volume": 638900000,
    "fcf_positive": true,
    "cash_runway_months": null,
    "funding_secured": null,
    "share_count_growth_yoy_pct": 2.1,
    "revenue_growth_yoy_pct": 21.8,
    "prior_year_quarter_revenue_usd": 478000000,
    "integrity_red_flag": false,
    "dilution_from_acquisition": null
  },
  "judged": {
    "fundamental_quality":    {"score": 7, "evidence": "[FACT] rev +21.8% YoY (10-Q Q2 FY27); [FACT] FCF positive 4 straight quarters"},
    "valuation_dislocation":  {"score": 6, "evidence": "[FACT] -19% from 52w high after a beat-and-drop; [ASSUMPTION] EV/S ~8x vs 5y median ~12x"},
    "catalyst_strength":      {"score": 6, "evidence": "..."},
    "downside_survivability": {"score": 7, "evidence": "..."},
    "technical_setup":        {"score": 5, "evidence": "..."},
    "sentiment_positioning":  null
  },
  "market": {
    "rsi14": 48.5, "pct_above_50dma": -4.1, "hv30": 0.52,
    "atm_iv": 0.49, "iv_rank": null,
    "days_to_earnings": 71, "days_to_nearest_catalyst": 44
  },
  "catalyst_horizon_days": 420,
  "contracts": {
    "short_call": {"expiration": "2026-12-18", "dte_days": 88, "strike": 340, "delta": 0.71,
                   "bid": 57.2, "ask": 58.6, "open_interest": 612, "implied_volatility": 0.50},
    "csp":        {"expiration": "2026-10-30", "dte_days": 39, "strike": 350, "delta": 0.24,
                   "bid": 9.6, "ask": 9.95, "open_interest": 431, "implied_volatility": 0.51},
    "leap":       {"expiration": "2028-01-21", "dte_days": 852, "strike": 300, "delta": 0.77,
                   "bid": 131.0, "ask": 134.5, "open_interest": 540, "implied_volatility": 0.47}
  }
}
```

A contract you couldn't price is omitted or `null`, and that vehicle fails its `contract` gate. Add
a `deep_dive` block only for a deep dive (see `structures.md`).

**A name that plainly fails a disqualifier** needs only the name block. For example, a leveraged ETF:

```json
{"ticker": "TQQQ", "instrument_type": "etf",
 "name": {"avg_daily_dollar_volume": 3740000000, "leveraged_or_inverse": true,
          "aum_usd": 39700000000, "expense_ratio_pct": 0.82}}
```

Dollar volume is the 30-day average volume times the last close. The `technicals` helper computes it
from `{"closes": [], "last_close": ..., "avg_volume": ...}` if you'd rather not do it by hand.

## Field sources

### context
| Field | Source |
|---|---|
| `quotes_live` | Regular session open (9:30–16:00 ET, trading day) **and** option quotes' `updated_at` within a few minutes. Otherwise `false`. |
| `option_level` | `get_accounts` → the account matching `portfolio.account_ref` in `state/config.yaml` → its `option_level` string, verbatim. |
| `leverage_mode` | `true` only if the user explicitly asked for leverage or OTM calls. |

### name — stocks
| Field | Source |
|---|---|
| `avg_daily_dollar_volume` | From the `technicals` helper (average volume × last price). |
| `fcf_positive` | Operating cash flow minus capex, trailing twelve months. Concepts: `NetCashProvidedByUsedInOperatingActivities` and `PaymentsToAcquirePropertyPlantAndEquipment` (some filers use `PaymentsToAcquireProductiveAssets`). A 10-Q only has year-to-date figures, so TTM = last fiscal year (10-K) + this year's YTD − last year's YTD (the 10-Q carries both YTDs). Say which periods you used. |
| `cash_runway_months` | Only when FCF is negative: cash and short-term investments ÷ monthly burn. |
| `funding_secured` | Only when FCF is negative: a closed raise or committed facility that covers the gap. `null` if not found. |
| `share_count_growth_yoy_pct` | Same 10-Q: `WeightedAverageNumberOfDilutedSharesOutstanding`, current vs prior-year period. The filing carries both. |
| `dilution_from_acquisition` | Only when share growth is over the limit: `true` if the jump comes from **one closed, stock-funded acquisition** (the 10-Q's business-combination note or the deal's 8-K shows shares issued as consideration). `false` for ongoing issuance: ATM programs, repeated raises, heavy stock comp. Serial stock-funded deals count as ongoing. Otherwise `null`. |
| `revenue_growth_yoy_pct` | `get_financials` (quarterly, limit 5): latest quarter vs the same quarter a year earlier. |
| `prior_year_quarter_revenue_usd` | That same year-earlier quarter's revenue, in dollars. Revenue growth only offsets dilution from a real base (config: $25M a quarter), so a jump from $61K to $5.5M can't justify 59% more shares. |
| `integrity_red_flag` | `true` for: an active SEC or DOJ investigation or enforcement action; a restatement or non-reliance 8-K (Item 4.02); an auditor resignation or going-concern paragraph; an exchange delisting notice; or a specific fraud allegation (for example a detailed short-seller report) that is **active**: made in the last 12 months, or followed by any of the official steps above. An older allegation with no official follow-up and clean audits since is a named risk in "Case against", not a flag; a company's boilerplate denial doesn't change that either way. A private securities class action over past statements doesn't count on its own, because they follow most large drops; mention it as a risk instead. Check `get_equity_news` (`limit: 8`; larger pages overflow) and one web search ("<ticker> SEC investigation OR restatement OR going concern"). `false` only after actually looking. |

### name — ETFs
| Field | Source |
|---|---|
| `leveraged_or_inverse` | Fund name and description (`get_equity_fundamentals`): 2x/3x/-1x/"Ultra"/"Bear"/daily-reset language. |
| `aum_usd` | `get_equity_fundamentals` `market_cap` (for an ETF that is its AUM). |
| `expense_ratio_pct` | Issuer page via web search. Use the **net** ratio (after any fee waiver), since that's what holders pay. `null` if not found. |
| `avg_daily_dollar_volume` | `technicals` helper. |

### market
| Field | Source |
|---|---|
| `rsi14`, `pct_above_50dma`, `hv30` | `technicals` helper output (`market` block). |
| `atm_iv` | The call `implied_volatility` at the strike nearest spot, in the monthly expiry closest to 30 DTE (at least 21), so it compares like-for-like with `hv30`. If that strike has zero open interest, use the nearest one that has some. Include it in a quote batch. The short call's IV-crush check uses that contract's own IV, so an expiry spanning earnings is judged on its real price. |
| `iv_rank` | Only if a source actually reports it. Robinhood doesn't; leave `null` and the engine uses `atm_iv / hv30`. Never estimate it. |
| `days_to_earnings` | `get_earnings_results` → next report date − today, in calendar days. For an ETF leave it `null`: ETFs don't report, and the engine treats `null` there as no event rather than an unknown one. |
| `days_to_nearest_catalyst` | The nearest **dated** catalyst of any kind: earnings, product launch, investor day, FDA date, index inclusion. From news or web search. `null` if nothing is dated. |

### catalyst_horizon_days
When the multi-catalyst thesis should have visibly played out, in calendar days from today. It is a
judgment call, so give the reason in your output. The LEAP must expire after it (v7's catalyst
duration check), which is also why long theses get long expiries.

### contracts
Each: `expiration`, `dte_days`, `strike`, `delta` (absolute value, so a put's −0.24 is `0.24`),
`bid`, `ask`, `open_interest`, `implied_volatility`, all straight from `get_option_quotes`. How to
choose them is in `structures.md`.

## The `technicals` helper

1. `get_equity_technical_indicators` × 3, each with `interval: day`, `output: latest`, and
   `start_time` about 400 days back: `type: rsi` (period 14), `type: sma` (period 50),
   `type: sma` (period 200).
2. `get_equity_fundamentals`: `high_52_weeks`, `average_volume_30_days`.
3. `get_equity_historicals` with `interval: day` and `start_time` about 46 calendar days back
   (≈31 sessions). Take the `close_price` values of non-interpolated bars, oldest first.
   **After the close:** for a few hours Robinhood's daily bars and indicators end at the previous
   session. If today's bar is missing, append today's closing trade from `get_equity_quotes` to
   `closes`. RSI and the moving averages will be one session stale; say so in the output rather
   than patching them.
4. Write this to `<workdir>/tech/<TICKER>.json` (a `tech/` subfolder, so the screen's `*.json`
   glob never picks it up), filling in the numbers you fetched:

```json
{"closes": [...], "last_close": null, "rsi14": 48.52, "sma50": 391.2, "sma200": 332.8,
 "high_52w": 473.1, "avg_volume": 1910415}
```

(`last_close: null` means use the last close in the list; pass the live quote instead during market
hours.)

5. `python3 -m engine.vehicle technicals <workdir>/tech/<TICKER>.json` returns three blocks. Copy
   `market` into the input file's `market`, and `name` into its `name`. `for_judgment` is
   evidence for the valuation-dislocation and technical-setup calls, not an engine input: distance
   from the 52-week high and the 200-day average, plus `hv30_untrimmed`. The engine's `hv30`
   drops the single largest move in the window, so one earnings gap doesn't make options look
   cheap.
