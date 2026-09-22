---
name: stock-screen
description: Screen any stock, ETF or closed-end fund, one ticker or a list, and pick the best vehicle for it (shares, a short-dated call, a cash-secured put, or a LEAP), with a deterministic 0-100 score that ranks names against each other, a one-screen decision matrix, and an on-request deep dive with scenarios, expected geometric return and sizing. Use this whenever the user names tickers and asks whether to buy, how to play a name, shares vs options vs LEAPs, "is X a buy", "quick take on X", "compare/rank these", "stock-screen X", or "deep dive X", even if they don't say "screen". Not for v7's own runs: "run the daily screen"/"screen today" belongs to daily-screen, and "does X fit v7 / the watchlist" belongs to bench-check.
---

# Stock Screen — which vehicle, and how the name ranks

This skill answers a question v7 deliberately doesn't: for **any** stock, ETF or closed-end fund, which vehicle fits
best — shares, a 30–90 day call, a cash-secured put, or a LEAP — and how does the name rank against
others. It sits beside the v7 skills rather than competing with them (ADR 0019):

- **You gather evidence and make six judgment calls.** Everything arithmetic — disqualifiers, the
  volatility score, the extension cap, per-vehicle weights, penalties, confidence, ranking, scenario
  math, sizing — happens in `engine/vehicle.py`. Don't recompute any of it in prose. The point is
  that the same inputs always produce the same score, so a name screened today ranks honestly
  against one screened last week.
- **The LEAP row borrows v7's rules.** Its DTE band, spread and open-interest floors, and the §13.1
  delta policy come from v7's config, and the regime comes from v7's cached macro state. The LEAP
  row is **never sized here**: v7 owns LEAP sizing through `bench-check` and `daily-screen`.
- **Missing data is bounded, not guessed.** Leave any input you couldn't establish as `null`. The
  engine scores a missing factor at 0 for the floor and 10 for the ceiling, ranks on the floor, and
  lowers confidence as the gap widens. A guessed number would silently look as trustworthy as a
  real one; a `null` shows up as a wider gap and lower confidence.

Output vocabulary is `BEST FIT: <vehicle>`, `PASS`, `INCOMPLETE` or `DISQUALIFIED`, never
`CANDIDATE` (that word belongs to v7's daily screen) and never "buy". `INCOMPLETE` means the gaps
in the data decide the verdict: some vehicle's floor is below the pass line but its ceiling is at or
above it. Report it as such, name the missing inputs, and say what fetching them would settle.
This is structured analysis for the user's own decision.

## Setup — once per run

1. **Paths.** Run the engine from this repo's root (`python3 -m engine.vehicle ...`). The private
   data repo is normally the sibling checkout `../leaps-hunter-data`. If it isn't there, ask the
   user once for its path. You need three files from it: `state/config.yaml` (v7 config plus
   `portfolio.account_ref`), `state/macro-latest.json`, `state/watchlist.json`. Read them; never
   write to the data repo from this skill.
2. **Working directory.** Use your scratchpad directory if the session has one, otherwise
   `${TMPDIR:-/tmp}`, under `stock-screen/<YYYY-MM-DD>/`, with three parts: `inputs/` (one
   `<TICKER>.json` per name), `tech/` (helper files), and `screen.json` (the engine's output).
   Keeping the output out of `inputs/` matters: the screen reads every file there. Keep the inputs
   too; they're what makes a result replayable.
3. **Options level.** Only the cash-secured put uses it, so look it up once a name has cleared
   its disqualifiers. Call `get_accounts` and read `option_level` for the account whose
   `account_number` matches `portfolio.account_ref` in `state/config.yaml`. Use that account
   only; don't infer one (ADR 0013's lesson). If `account_ref` is null, leave `option_level` null
   and the CSP row will fail closed.
4. **Session.** `quotes_live` is `true` only during the regular session (9:30–16:00 ET, trading
   day) with option quotes updated in the last few minutes. Check with
   `TZ=America/New_York date` and the quotes' `updated_at`. After hours, set `false`: the engine
   then treats wide spreads as warnings to re-check at the open instead of vetoes, because closing
   spreads over-reject. Robinhood's daily bars and indicators also lag a session for a few hours
   after the close; `references/inputs.md` says how to handle that.
5. **Leverage mode** is on only if the user explicitly asked for leverage or OTM calls. It lets the
   short-dated call go down to 0.30 delta, labeled `LEVERAGE`. It never loosens the LEAP row:
   v7 prohibits sub-0.55-delta single-name LEAPs.

## Step 1 — gather inputs for each ticker

Build `<TICKER>.json` following the schema in `references/inputs.md`, which also maps every field to
the tool that supplies it. Expect roughly 30–40 tool calls per ticker in quick mode, about a
third of them option-contract lookups, so a four-name ranking runs past 100. Issue independent
calls in parallel: they don't depend on each other.

**Disqualifiers first.** Establish the name-level facts before anything else, and if one plainly
fails (a 3x ETF, a going-concern paragraph, 40% dilution with no revenue base), run the screen on
just that block and stop gathering. The engine won't score a disqualified name, so technicals,
chains, the account lookup and judgment calls for it are wasted work. `references/inputs.md`
shows the minimal file for this case.

- **Stock, ETF or closed-end fund?** `get_equity_fundamentals` (profile, 52-week high, average
  volume, market cap). An ETF's market cap is its AUM. A profile that says "closed-end management
  investment company" is a closed-end fund (`instrument_type: "cef"`). Its price floats free of
  its holdings, so its market cap is *not* its assets: use NAV × shares.
- **Name-level disqualifiers** (stocks): free cash flow sign and runway, share-count growth YoY
  (and whether a jump came from one stock-funded acquisition), revenue growth YoY, integrity
  flags. Latest 10-Q via `get_sec_filing_index` → `get_sec_filing_facts`, plus `get_financials`.
  ETFs instead: leveraged/inverse, AUM, expense ratio. Closed-end funds: NAV per share and its
  date (for the premium or discount to NAV, and how stale that is), net assets, expense ratio,
  integrity.
- **Technicals:** Robinhood's `get_equity_technical_indicators` with `output: latest` for RSI14,
  SMA50 and SMA200. For 30-day realized vol, pull ~31 sessions with `get_equity_historicals` and
  hand the closes to `python3 -m engine.vehicle technicals <workdir>/tech/<TICKER>.json`, which
  computes `hv30`, `pct_above_50dma`, `pct_from_52w_high` and dollar volume. Don't pull a year of
  bars: that's ~40KB per ticker for numbers the indicator tool returns in one line.
- **Dates:** next earnings from `get_earnings_results`, other dated catalysts from
  `get_equity_news` and web search.
- **Contracts:** one live contract per option vehicle. See `references/structures.md` for expiry
  and delta targets and the cheap way to walk a chain. Also note the at-the-money IV from the
  monthly expiry closest to 30 DTE: it becomes `market.atm_iv`.

## Step 2 — make the six judgment calls

Score `fundamental_quality`, `valuation_dislocation`, `catalyst_strength`,
`downside_survivability`, `technical_setup` and `sentiment_positioning` from 0 to 10 against the
anchors in `references/scoring.md` (it has an ETF column too). Write each one as
`{"score": 7, "evidence": "..."}` with `[FACT]` or `[ASSUMPTION]` on each piece of evidence. When
you couldn't find the evidence for a factor, write `null` — don't default to 5.

Judge the business and the setup, not the vehicles. Vehicle fit is what the weights are for; if
you shade `catalyst_strength` up because you already like the short call, you are counting the
same evidence twice.

## Step 3 — run the screen

```bash
python3 -m engine.vehicle screen \
  --v7-config ../leaps-hunter-data/state/config.yaml \
  --macro ../leaps-hunter-data/state/macro-latest.json \
  --watchlist ../leaps-hunter-data/state/watchlist.json \
  <workdir>/inputs/*.json > <workdir>/screen.json
```

It returns the macro context (regime, active hard gates, a staleness banner) and every ticker
ranked, with per-vehicle gates, warnings, score floor/ceiling, confidence and labels, plus
`factor_bounds.notes`: whether the extension cap applied, what the volatility score came from,
and any bounded factors. If a file fails to parse, fix the file; don't work around the engine.

Confidence comes from the gap between floor and ceiling, with one more rule: option vehicles are
capped at Med while quotes aren't live, since closing spreads and marks can move at the open. Say
so when it's the reason.

## Step 4 — report (quick mode, the default)

Build every number from the engine's JSON. The report reads top to bottom as a story: where the
name stands, what each vehicle offers, which one fits and why. Keep one ticker to about one
screen:

```
STOCK SCREEN — <date> <HH:MM ET> — v7 regime: <RESTRICTED R=3 | NORMAL | UNKNOWN> — quotes: <live | closed market>
<STALE MACRO CONTEXT banner, if the engine returned one>

<TICKER> · <Full company name> — BEST FIT: <vehicle> — <composite> (ceiling <c>) — Confidence: <High|Med|Low>
   (or: — PASS — <composite> (ceiling <c>) — Confidence: …   or: — INCOMPLETE — <floor>–<ceiling>)
Short answer: <one sentence that answers the user's actual question>

**Where it stands**
- Price: <close>, <x>% below the 52-week high, <above/below> the 50- and 200-day averages; RSI14 <r>, extension cap <applied / not applied> [FACT]
- What moved it: <the cause of the recent move, from news or filings> [FACT]
- Business: <growth, margins or FCF, balance sheet, in one line> [FACT]
- Valuation: <multiple against its own history or peers> [FACT] / [ASSUMPTION]
- Next dated catalysts: <event, date; event, date>

**The vehicles**
| Vehicle | Score | Structure | Max loss | Key risk | Why |
|---|---|---|---|---|---|
| Shares | 72 | at $383.56 | −44% to the 52-week low ($215.68) | ... | ... |
| Short call | 58 ✗ quoted_spread | Dec-18 $340C Δ0.71 · $48.90 ask | $4,890 / contract | ... | ... |
| Cash-secured put | 66 | Nov-20 $350P Δ0.24 · $9.70 bid | assigned at $340.30 net | ... | ... |
| LEAP | 76 | Jan-28 $300C Δ0.77 · $118 ask | $11,800 / contract | ... | OUTSIDE v7, UNSIZED |

**How to play it**
- Best fit: <vehicle and structure>. Why it wins, in terms of the factors that drove its score.
- Runner-up: <vehicle> at <score>, and when it would be the better choice.
- Timing: <anything to wait for: a re-check of spreads at the open, an earnings date, a level>.

**Case for:** 1. ... 2. ...   **Case against:** 1. ... 2. ... 3. ...   (each tagged)
**What would change my mind:** <one or two specific, observable triggers with levels or dates>

Deep dive? Say "deep dive <TICKER>".
Sources: <links for anything taken from web search>
```

- Use the full company name next to the ticker; the fundamentals profile's description opens with
  it. For an ETF, use the fund's name.
- Keep "Where it stands" factual: it's the base the rest of the report argues from. Judgments
  belong in "How to play it" and the case for and against.
- Carry the engine's `factor_bounds.notes` into the report where they explain a score: the
  extension cap, the volatility basis (e.g. "ATM IV / HV30 1.13"), an IV-crush penalty.
- Scores, gates and sizes come from the engine. Simple figures derived from quoted fields
  (breakeven, time value, net price if assigned, distance to the 52-week low) are fine to compute
  yourself; show the inputs so they can be checked.
- Show a failing gate right in the Score cell (`58 ✗ delta`); an ineligible vehicle can't be the
  best fit whatever its score.
- Carry the engine's warnings, e.g. an earnings date inside a CSP's expiry or a provisional
  spread, into Key risk.
- The LEAP row's label comes from the engine: `ON v7 WATCHLIST (...)` means run `bench-check`
  for v7's verdict and size; `OUTSIDE v7, UNSIZED` means propose the name for Stage A if it holds
  up.
- Quick mode has no scenarios, so the Shares max-loss cell uses a fetched reference: the 52-week
  low, or a named support level. Scenario-based losses belong to the deep dive.
- **Disqualified names:** the header, then one line naming the failed check and its reason, with
  the figures behind it (share counts and revenue for dilution, cash and burn for runway).
  Nothing is scored, by design, and the whole reply stays under about ten lines. If the user asked
  a direct question ("LEAPs or shares?"), add two or three tagged facts showing why that check
  matters for this name (for a leveraged ETF, its return against the multiple of the index it
  tracks over the past year). Then name the cleaner way to express the same view, such as the
  unleveraged underlying, and offer to screen it. Don't score, price or model the disqualified
  name: the point of disqualifying first is not spending effort on it.

**Several tickers:** one ranked table first (rank, ticker and company name, composite, best
vehicle, confidence, top risk), in the engine's order. Then, per name, the verdict line, one
"where it stands" sentence, and one sentence on why its best fit wins. Skip the per-name matrices
unless the user asks for them. Disqualified names go at the bottom with their reason.

## Deep dive (on request)

Read `references/structures.md` § Deep dive. In short:

1. Write bull/base/bear price scenarios (add a tail case if it matters) for each eligible vehicle's
   horizon, with explicit probabilities that sum to 1 and a one-line basis for each. These are
   `[ASSUMPTION]`s and must be labeled that way.
2. Add a `deep_dive` block to the ticker's file and run
   `python3 -m engine.vehicle deep-dive --v7-config ... --macro ... <file>`. It returns executable
   entry prices (never midpoints), scenario returns, EV, expected loss, Kelly f*, the
   regime-throttled fraction, EGR, and a size capped at the configured max loss. It returns
   `UNSIZED` for the LEAP.
3. Report: the full factor breakdown with evidence, the scenario table with EGR per vehicle, 2–3
   alternative strikes/expiries for the winning option vehicle if relevant, a dated catalyst
   calendar, sizing, and **kill criteria** (the specific conditions for exiting).

## Rules that don't bend

- **Read-only.** Never call any `place_*`, `review_*`, `cancel_*` or `exercise_*` tool, however
  the request is phrased (docs/annex-read-only.md; `.claude/settings.json` denies them anyway).
- **No invented data.** A number you didn't fetch is `null`, not an estimate. A training-data
  memory of a company isn't evidence of its current state.
- **Don't override the engine.** If a result looks wrong, say so and show which input drives it.
  Don't adjust the score by hand. If the rubric or weights are wrong, the fix is a change to
  `engine/stock_screen.yaml` with a reason, made deliberately.
- **Don't write to v7 state.** `stock-screen` never touches `state/calibration.json`, the
  watchlist, or daily records.
