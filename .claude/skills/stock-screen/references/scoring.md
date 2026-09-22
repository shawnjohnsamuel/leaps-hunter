# The six judgment calls — anchors

Each factor is 0–10. The anchors below are what keeps a "7" meaning the same thing on different
days and different names. Without them, scores drift and cross-ticker ranking stops holding. Pick
the band whose description fits the evidence, then place the score inside the band by how
strongly it fits.

A few habits make the scores honest:

- **Score the evidence you have, not the story.** Each score carries evidence tagged `[FACT]`
  (fetched this session, with its source) or `[ASSUMPTION]` (your inference). A factor resting
  entirely on assumptions should rarely go above 6.
- **`null` beats a guess.** If you couldn't find the evidence for a factor, write `null`. The
  engine bounds it at 0–10 and lowers confidence. A made-up 5 would pass for knowledge.
- **Judge the business and setup, never the vehicle.** Vehicle fit is what the per-vehicle
  weights in `engine/stock_screen.yaml` are for.
- **Two factors are partly mechanical.** The engine caps `technical_setup` at 3 when RSI14 ≥ 75 or
  price is ≥ 20% above the 50-day average, whatever you score it. It computes
  `volatility_pricing` itself, so there's no judgment call for option cheapness.

For ETFs, apply each anchor to the basket and the structure, as the ETF notes describe.

**Closed-end funds** follow the ETF notes, with four differences:
- `valuation_dislocation` reads the **discount to NAV against the fund's own history** as well as
  the holdings' valuation. A discount well wider than its one-year average is a dislocation (7–8).
  A premium scores 3 or lower, since you'd be paying more than the holdings are worth.
- `fundamental_quality` includes how verifiable the NAV is. Holdings priced daily in public
  markets beat quarterly marks on private companies, whatever those companies are.
- `downside_survivability` weighs structural leverage (borrowing or preferred shares),
  concentration, and whether the discount can widen further in a selloff. For CEFs it usually can.
- `catalyst_strength` counts tender offers, buybacks below NAV, a holding's IPO or sale, and
  activist pressure on the discount. A rights offering is dilutive and works against you.

---

## fundamental_quality — growth, margins, balance sheet, cash generation

| Score | Looks like |
|---|---|
| 0–2 | Revenue shrinking, margins negative or deteriorating, burning cash with debt maturing |
| 3–4 | Flat or low growth, or growth bought with widening losses; thin margins; meaningful leverage |
| 5–6 | Steady high-single to low-double-digit growth, positive but unremarkable margins, manageable debt |
| 7–8 | Double-digit growth with high or expanding margins, FCF positive, net cash or low leverage |
| 9–10 | Durable 20%+ growth *and* high FCF margins *and* net cash. Rare. |

**ETF:** earnings growth and profitability of the top holdings, weighted. A broad quality index sits
around 6–7. A basket of unprofitable growth names sits around 3–4 however hot the theme.

## valuation_dislocation — how far price sits below what intact fundamentals justify

| Score | Looks like |
|---|---|
| 0–2 | Priced for perfection: multiple at or near its own historic high after a run, no room for error |
| 3–4 | Full valuation, trading near highs |
| 5–6 | Fair: in-line multiple, or a modest pullback |
| 7–8 | Clear dislocation: 20–40% off highs, or a multiple well below its own history and peers, **with fundamentals intact** (beat-and-drop, sector-wide selloff, forced selling) |
| 9–10 | Extreme dislocation with *verified* intact fundamentals (panic, index deletion, liquidation). Rare. |

The discount has to be to intact fundamentals. A cheap multiple on a business that is deteriorating
is a value trap and scores 4 or lower. Ask "why is it down?" and cite what you found.

**ETF:** the basket's aggregate valuation against its own history, and the drawdown of the whole
theme. A sector ETF down 30% on a cyclical scare, with earnings holding, is a 7.

## catalyst_strength — how many, how independent, how soon

| Score | Looks like |
|---|---|
| 0–2 | Nothing identified |
| 3–4 | One vague or distant catalyst ("AI tailwinds", "someday margins improve") |
| 5–6 | One concrete, dated catalyst, or two soft ones |
| 7–8 | Two or more **independent** catalysts, at least one dated within ~6 months |
| 9–10 | Several independent, dated, high-impact catalysts. Rare. |

**A single binary event caps this factor at 5** however large it is: one FDA decision, one contract
award, one court ruling. Independence is the point, because one failure shouldn't sink the whole
thesis.

**ETF:** macro and sector catalysts that move the basket (a rate-cut path, a capex cycle,
legislation). Stock-specific news rarely counts.

## downside_survivability — what the bad case actually does

| Score | Looks like |
|---|---|
| 0–2 | The bad case is permanent impairment: dilutive raise, covenant breach, business model broken |
| 3–4 | The bad case is a deep drawdown with a slow recovery: leverage, customer concentration, or one product |
| 5–6 | The bad case is a cyclical drawdown; the balance sheet holds |
| 7–8 | Net cash, recurring revenue, diversified customers: the bad case is a de-rating, not a break |
| 9–10 | Fortress: net cash, essential product, pricing power. Hard to see a permanent loss. |

This is the factor that should most often keep you out of trouble. A great story on a fragile
balance sheet loses to a boring name that can't blow up.

**ETF:** broad, unleveraged index 7–9; sector ETF 5–7; narrow thematic or single-country 3–6.

## technical_setup — the quality of the entry, read contrarian

| Score | Looks like |
|---|---|
| 0–2 | Breaking down: below a falling 200-day, lower lows, no support in sight |
| 3–4 | Extended (the engine caps this anyway), or chopping inside a downtrend |
| 5–6 | Neutral: mid-range, no clear edge |
| 7–8 | Pulled back to real support (the 200-day, a prior breakout level) inside an intact long-term trend, momentum stabilizing (RSI recovering from below 40) |
| 9–10 | Capitulation-style washout at major support with a confirmed reversal. Rare. |

Use `for_judgment` from the `technicals` helper (distance from the 52-week high and from the 200-day)
and the RSI. Name the support level you mean.

## sentiment_positioning — who is already in, read contrarian

| Score | Looks like |
|---|---|
| 0–2 | Crowded long: near-universal Buy ratings, price above most targets, heavy insider selling |
| 3–4 | Consensus bullish, little room left for upgrades |
| 5–6 | Mixed |
| 7–8 | Skeptical sentiment against improving facts: downgrades after a drop, price well below the average target, insider buying, elevated short interest heading into catalysts |
| 9–10 | Capitulation sentiment plus clustered insider buying. Rare. |

Sources: `get_equity_analyst_ratings` (ratings mix and targets), news for insider buys and short
interest. If you have none of the three, it's `null`, not a 5.

**ETF:** fund flows and positioning in the theme, if you can find them; otherwise `null`.
