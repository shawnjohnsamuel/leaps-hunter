# ADR 0022: A share fallback and a spread path for clears the account can't hold as LEAPs

**Status:** accepted (2026-11-03) · **Extends:** §13.3 (account feasibility), §13.2 (spread
rule), [ADR 0013](0013-paper-ledger-and-nav-integrity.md), [ADR 0021](0021-pipeline-overhaul-after-50-sessions.md)

## Context

Micron Technology (MU) cleared every gate on 2026-11-02 and 11-03 and was rejected at §13.3: one
Jan-2028 $600 call cost about $37,750, roughly 100% of the account's NAV. The risk model's own
robust-Kelly size (0.125 × f_robust) was 6.3% of NAV, so no cap setting would have bought a
contract. Estimated against current prices, a 0.70–0.85 delta LEAP on every watchlist name
costs 10–90% of NAV.

The user's goal is output they can act on. They asked for a shares alternative and applied for
Robinhood options level 3 (the account is level 2, which can't hold spreads).

Spreads help less than expected. §13.2 requires `Pr(S_T > K_short) ≤ 25%`, which puts the short
strike well above spot. Priced with Black-Scholes on 2026-11-03, a compliant spread costs 55–65%
of the outright: about 6% of NAV for ServiceNow, 9–16% for most names, 47% for MU. Narrow, cheap
spreads would violate the rule.

## Decision

**Share fallback** (`engine.sizing.share_fallback`, config `share_fallback`). When a name clears
everything through §13.2 but neither the outright nor a spread fits (§13.3), report what the same
clear means as shares:
- **Same story.** Probabilities and underlying moves come from the §12.3 scenarios the LEAP was
  priced on.
- **Same sizing method.** Robust Kelly over posterior draws, capped at 1.0 (no margin), times the
  regime multiplier.
- **Its own loss cap.** `share_fallback.max_loss_pct_nav` of NAV lost if the worst scenario plays
  out. The default is 0.25%, the user's 2026-09-21 choice for stock-screen's share sizing. It is
  the binding limit at today's settings, and the user's to change.
- **Same acceptance tests.** §12.3's EV, EV/EL and log-growth tests, applied to the share
  returns.
- **Labeled and tracked.** A pass is a *share candidate*, reported as analysis, never an
  instruction. The worst-scenario price is a §16 review trigger, not an automatic stop.
  `fail_category` stays `s14_infeasible`. The block rides on the calibration entry, and
  `weekly-review` marks the share price beside the contract's bid, so each vehicle builds its own
  record.

**Spread path** (`engine.optmodel.prob_above`, `min_short_strike`, `spread_debit`,
`spread_returns`). §13.3 already says to evaluate a spread when the outright is infeasible; this
supplies the numbers. It runs only when `get_accounts` reports `option_level_3`, sizes with the
same §14 chain and caps as the outright, and must pass all five §13.2 conditions.

**Sanitizer.** `result` is `CANDIDATE` only when a name's `fail_category` is `cleared`. Counting
§11 clears would have published 2026-11-02 and 11-03 as candidates with an empty list.

## Consequences

- With today's 0.25% share cap, MU's clear would have read about $314 of shares (0.38 shares),
  losing $94 in the bear case. At 1% it would be about $1,256, at 2% about $2,511. The risk model
  alone would allow 12.5% of NAV.
- Spreads mostly won't fit at the 0.25%/1.25% option caps either. They become relevant if the
  user raises those caps; that, like the share cap, is a risk decision this ADR doesn't make.
- Nothing about what clears changes. Only what a clear produces does.
