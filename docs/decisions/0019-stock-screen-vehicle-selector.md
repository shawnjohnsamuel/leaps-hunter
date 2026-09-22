# ADR 0019: `stock-screen` picks a vehicle for any ticker, and borrows v7's LEAP rules

**Status:** accepted (2026-09-21) · **Extends:** [ADR 0010](0010-deterministic-engine.md)

## Context

v7 answers one question, narrowly on purpose: does a watchlist name clear a mechanism-gated,
regime-throttled bar for a long-dated call right now. It says nothing about shares, short-dated
options, puts or ETFs, and `bench-check` refuses to score an off-watchlist name.

The user wanted a general tool: drop in any stock or ETF (or a list of them) and get the best
vehicle, a score that ranks across names, a one-screen decision matrix, and a deep dive on
request. A first draft of that skill, written in a chat session with no knowledge of v7, had
four problems in this repo:

1. **A second, conflicting LEAP rulebook.** It said "ITM-first, OTM when I ask for leverage."
   v7 §13.1 sets 0.60–0.85 delta (0.70–0.85 restricted) and prohibits anything under 0.55 for
   single-name LEAPs. The same ticker could have come back with two different strikes.
2. **A way around v7's sizing.** It sized by "% of risk capital, driven by confidence." §14/§17
   cap every position at 0.25% of NAV until 50 calibration observations exist.
3. **No regime awareness.** It never read the R throttle, which as of today is restricted.
4. **Model-judged 0–10 scores with no arithmetic anchor.** That is the v6 rubric pattern ADR
   0010 replaced. Scores would drift between sessions, so cross-ticker ranking — the point of
   the score — would not hold.

It also had no path for ETFs, and its only answer to expensive options was "don't buy them."

## Decision

**1. A fifth skill, `stock-screen`, backed by `engine/vehicle.py`.** Four vehicles: shares, a
short-dated call, a cash-secured put, and a LEAP. The CSP is the vehicle that benefits from
expensive options and fits the user's buy-the-dislocation style. `bench-check` keeps "does this
fit v7"; `stock-screen` answers "which vehicle."

**2. ADR 0010's split, applied again.** The model makes six judgment calls (fundamental quality,
valuation dislocation, catalyst strength, downside survivability, technical setup, sentiment),
each 0–10 against a written rubric with its evidence attached. The engine does everything else:
hard disqualifiers, volatility pricing (from IV rank, or ATM IV against 30-day realized vol),
the extension cap on technical setup, per-vehicle weights, IV-crush and missing-catalyst
penalties, confidence, ranking, and the deep-dive scenario math.

**3. Missing data is bounded, not guessed.** A factor the model couldn't assess counts as 0 for
the score's floor and 10 for its ceiling. The floor ranks; the gap sets confidence. This is the
bounding `daily-screen` used on 2026-09-03 for an unpriced §11 dimension. Every gate fails
closed on a missing input.

**4. The LEAP row reads v7's config, not its own.** DTE band, spread, open interest and the §13.1
delta policy come from v7's config, and the regime comes from `state/macro-latest.json`, read
and never recomputed. An active §6.1 hard gate blocks the row, and unknown macro state fails it.
So `stock-screen` can never call a LEAP permissible that v7 would reject.

**5. LEAPs are never sized here.** The LEAP row is labeled `ON v7 WATCHLIST` (run `bench-check`
for the real verdict and size) or `OUTSIDE v7, UNSIZED` (propose for Stage A). The user chose to
still show the strike and expiry off-watchlist, so the skill is useful for exploring without
creating a way around v7's sizing.

**6. Other vehicles are sized at min(throttled Kelly, a max-loss cap).** The Kelly multiplier is
v7's regime throttle (0.25 normal, 0.125 restricted or unknown). The cap defaults to v7's 0.25%
NAV unvalidated-setup cap for every vehicle, since `stock-screen` has no calibration record
either. The user can raise it in `engine/stock_screen.yaml`, deliberately.

**7. Its own config file.** `engine/stock_screen.yaml` holds every stock-screen threshold and
weight. Adding them to `config.example.yaml` would widen the gap between that file and v7's §20
for rules that aren't v7's.

## Consequences

- Same inputs, same score: an input file saved from one run replays to an identical result.
- Closed-market spreads become warnings to re-check at the open rather than vetoes (the 2026-07-08
  run 1 lesson), and option confidence is capped at Med until quotes are live.
- Leveraged and inverse ETFs are disqualified outright: daily-reset decay applies over every
  holding period this skill screens for.
- Every default weight and threshold is an `[ASSUMPTION]`. None has an out-of-sample record, and
  `stock-screen` does not write to `state/calibration.json`, which stays scoped to v7 candidates.

## Amendments after the first test round (2026-09-21)

Three test runs against live data, each paired with a run without the skill, changed four rules:

- **HV30 drops its single largest daily move** (`factors.volatility_pricing.hv_trim_largest_moves: 1`).
  Straight after earnings, the gap day inflated realized vol, so options on MDB and NVDA read as
  cheap. Trimming errs toward "not cheap", the safe direction for a buyer. NVDA's short call fell
  from 67 to 63 on replay; MDB didn't move.
- **A one-time, stock-funded acquisition passes the dilution check**
  (`dilution_from_acquisition`). CEG's 14.7% share growth came from the Calpine deal. The rule
  was written for ongoing issuance, and serial stock-funded deals still count as ongoing.
- **ETFs have no earnings.** For an ETF a missing earnings date means none, not unknown, so the
  short call takes no IV-crush floor penalty.
- **`INCOMPLETE` joins the verdicts.** A PASS must hold whatever the missing inputs turn out to
  be. When any eligible vehicle's ceiling reaches the pass line, the gaps decide, and the screen
  says so instead of guessing PASS.

## Amendments after the second test round (2026-09-21)

- **Ties lean toward upside: LEAP → shares → short call → put** (`verdict.tie_break_order`). The
  user's choice. Upside comes first, but a tie never lands on the vehicle most likely to expire
  worthless within weeks, and the put goes last because its upside is capped at the premium.
- **IV crush is judged on the contract being bought.** PLTR's Nov-20 call spanned earnings at 58%
  IV against 42% realized, while the 30-day ATM IV (47.5%) read "not expensive", so no penalty
  applied. The check now uses the contract's own IV when it's known. On replay the call fell from
  53 to 38.
- **Revenue growth offsets dilution only from a real base**
  (`dilution_offset_min_prior_quarter_revenue_usd: 25000000`). QUBT's shares rose 58.9% and
  passed on +9,000% revenue from a $61K quarter, mostly acquired.
- **Fraud allegations must be active to disqualify.** "Active" means made within 12 months or
  followed by an official step: a regulator inquiry, a restatement, an auditor resignation or
  going-concern paragraph, or a delisting notice. QUBT's January 2025 short report had none of
  these, which left the flag to a judgment call that could flip between runs. It now counts as a
  named risk, and QUBT is disqualified on dilution instead, an objective reason.
- **`strike` helper** (`python3 -m engine.vehicle strike`). The rough starting-strike rule put
  MDB's Jan-28 0.76-delta call around $250; the helper gives $335, against $340 quoted.

