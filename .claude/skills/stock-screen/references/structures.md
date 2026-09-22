# Picking contracts, and the deep dive

## Contents
- Targets per vehicle
- Walking a chain cheaply
- Deep dive: scenarios, the `deep_dive` block, reading the output

## Targets per vehicle

| Vehicle | Expiry | Delta | Why |
|---|---|---|---|
| Short call | 30–90 DTE. Take the first standard monthly expiry (third Friday) of at least 30 DTE that still has the nearest dated catalyst inside it. If no catalyst falls within 90 days, take the monthly nearest 60 DTE; the engine applies the no-catalyst penalty either way. | Target 0.70 (gate 0.60–0.85). ITM-first: survivability over leverage. | An ITM call holds most of its value if the move is late or small. |
| Short call, leverage mode | Same | Target 0.40–0.50 (gate from 0.30). The engine labels it `LEVERAGE`. | Only when the user explicitly asked for leverage. |
| Cash-secured put | 21–60 DTE, ideally 30–45 | Target 0.25 (gate 0.15–0.35) | Pick the strike you'd be glad to own at: at or below real support, where valuation makes sense. The premium is a bonus, not the reason. |
| LEAP | v7's DTE band (365–900). Choose the expiry **after** `catalyst_horizon_days`: long theses get long expiries (a Jan-2028 over a cheaper Jan-2027 when the catalysts run late). | Restricted regime: target 0.75 (v7 band 0.70–0.85). Normal: target 0.70 (0.60–0.85). Never below 0.55: v7 prohibits it, leverage mode or not. | The engine checks it against v7's §13.1 policy for the current regime. |

**Starting strike.** Let the engine aim it:
`python3 -m engine.vehicle strike --spot 407.30 --delta 0.75 --dte 487 --iv 0.66` → $335 (MDB's
Jan-28 0.76-delta call was $340). Add `--put` for a put's absolute delta. Use the IV of a
nearby strike in that expiry; LEAP IV often sits well above short-dated IV, which is exactly where
rules of thumb miss. Round to the chain's grid, then quote two or three strikes around it; the
quoted delta is what counts.

## Walking a chain cheaply

1. `get_option_chains(underlying_symbol)` → the tradable chain's `expiration_dates`. Pick one
   expiry per vehicle from the table above.
2. **Look strikes up by exact value, not by listing the expiry.** A full listing pages upward from
   the lowest strike and runs ~30KB. Instead call
   `get_option_instruments(chain_symbol, strike_price="190.0000", expiration_dates="<d1>,<d2>")`.
   Omit `type` to get the call and the put at that strike, and pass several expirations at once
   when a strike serves more than one vehicle. Round your starting strike to the chain's grid
   (it widens for long expiries; a missing strike just returns nothing). Issue these lookups in
   parallel: two or three strikes around each target, plus the at-the-money strike.
3. One `get_option_quotes` call on the resulting ids (≤20 per call). Each quote carries bid, ask,
   delta, `implied_volatility`, `open_interest`, `updated_at`.
4. Take the strike whose delta is closest to the target **among those that pass liquidity**.
   During market hours that means spread and open interest. After the close, open interest is
   the only hard filter: spreads are provisional, and the engine only warns on them. Record its fields exactly as quoted; `delta` is the absolute
   value. If no strike passes, submit the one closest to target delta anyway: the engine then
   reports the failing gate, and the user can see exactly why the vehicle was ruled out.
5. The at-the-money strike's IV in the monthly expiry closest to 30 DTE is `market.atm_iv`.

About 8–12 calls for all three option vehicles. If an expiry's liquidity is hopeless (no bids, OI in
single digits), try one adjacent expiry and then stop. An unpriced or illiquid vehicle fails its
gate, which is the correct outcome, not something to search around.

## Deep dive

### 1. Scenarios

For each eligible vehicle, write price scenarios at that vehicle's horizon:

- **Shares and LEAP:** a 12-month horizon. For the LEAP, set `horizon_days.leap` to 365 so it's
  repriced with its remaining time value, not at expiry.
- **Short call and CSP:** at expiry, the default (the contract's `dte_days`).

Use at least bear/base/bull, and add a tail case when a real one exists (a failed binary event, a
guidance cut). Probabilities sum to 1. Every probability and price is an `[ASSUMPTION]`: give a
one-line basis for each (analyst range, prior drawdowns, the bad case you scored under
`downside_survivability`). Use the same underlying scenarios across vehicles where the horizons
match, so the comparison is between vehicles, not between stories.

### 2. The `deep_dive` block

```json
"deep_dive": {
  "spot": 383.56,
  "rate": 0.04,
  "dividend_yield": 0.0,
  "nav": null,
  "fees_per_share": 0.0,
  "horizon_days": {"leap": 365},
  "exit_iv": {"leap": 0.45},
  "scenarios": {
    "shares":     [{"label": "bear", "probability": 0.25, "price": 290},
                   {"label": "base", "probability": 0.50, "price": 430},
                   {"label": "bull", "probability": 0.25, "price": 540}],
    "leap":       [...],
    "short_call": [...],
    "csp":        [...]
  }
}
```

- `rate`: the current 3-month T-bill yield if you have it (`[FACT]`), otherwise 0.04 (`[ASSUMPTION]`).
- `nav`: only if the user gives it, or read live from `get_portfolio` on the configured
  `account_ref`. Never write NAV to disk anywhere except this temp file (ADR 0013).
- `exit_iv`: the IV you expect at the horizon; defaults to the contract's quoted IV. In a bear
  scenario IV usually rises, so set it higher if the bear case dominates.

Run `python3 -m engine.vehicle deep-dive --v7-config ... --macro ... <file>`.

### 3. Reading the output

Per vehicle:

- `entry`: executable, never the midpoint. A call pays the ask plus v7's slippage; a put collects
  the bid minus it.
- `returns`: per scenario, on the capital committed (share price, premium, or the put's cash
  collateral).
- `growth.ev`, `expected_loss`, `ev_to_el`: arithmetic edge and its ratio to expected loss.
- `growth.position_geometric_return`: the position's own geometric return at full size. For a long
  option with a total-loss scenario it's always −100%, which is exactly why sizing matters.
- `growth.kelly_f_star` and `fraction`: the growth-optimal fraction of NAV, and that fraction times
  v7's regime throttle (0.125 restricted, 0.25 normal).
- `growth.egr`: expected log growth of NAV per trade at `fraction`. **This is the number to compare
  across vehicles**, because it already accounts for how each one can lose.
- `size`: `min(throttled Kelly, max-loss cap)`, with `binding` naming which one won, `units` when
  NAV is known, and `min_nav_for_one_unit`. A zero with a large minimum NAV is a real answer: the
  vehicle is too big for the risk budget.
- The LEAP says `UNSIZED`. Point the user to `bench-check` (on the v7 watchlist) or a Stage A
  proposal (off it).

### 4. What the deep dive reports

- Every factor's score, the evidence behind it, and the engine's notes (caps, bounds, penalties)
- The scenario table: price, probability and basis per scenario, then return per vehicle
- EGR and EV/EL per vehicle, with the winner by EGR, and whether that agrees with the quick-mode
  score (say so if it doesn't, and why)
- 2–3 alternative strikes or expiries for the winning option vehicle, each with breakeven, delta,
  cost, intrinsic vs extrinsic, and its return in each scenario
- A catalyst calendar with dates
- Sizing from the engine, including `binding` and `min_nav_for_one_unit`
- **Kill criteria:** specific, observable exit conditions (a price level, a data point, a date) set
  now, before any position exists, so exiting isn't decided under pressure
