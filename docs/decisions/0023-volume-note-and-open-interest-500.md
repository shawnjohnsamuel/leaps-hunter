# ADR 0023: 20-day option volume becomes a note; open interest goes back to 500

**Status:** accepted (2026-11-04) · **Amends:** §12.1, [ADR 0021](0021-pipeline-overhaul-after-50-sessions.md)
(open interest and the mechanical `option_implementation` score) · **Relates to:**
[ADR 0004](0004-robinhood-sole-live-chain-source.md)

## Context

§12.1 vetoes a contract whose 20-day median daily volume is under 10. ADR 0021 made §11's
`option_implementation` mechanical, with that veto as one of four hard checks. Robinhood's option
bars carry no volume (its own tool says so), so the check failed closed on every name and capped
the dimension at 7, under its minimum of 10. On 2026-11-04 Micron Technology (MU) scored 80/80
and was blocked by this alone. Before ADR 0021 the dimension was scored by eye and volume was never
checked, which is how MU cleared on 11-02 and 11-03.

Better data doesn't fix it. Massive has per-contract volume but runs only on the user's Mac, out of
the cloud routines' reach. Over the 20 sessions to 2026-11-03, MU's two candidate LEAPs had medians
of 1.5 (Dec-2027 $650 call, traded 13 of 20 days, open interest 730, spread 3.7%) and 3.5
(Jan-2028 $600 call, 18 of 20 days, open interest 1,172, spread 3.9%). Deep in-the-money LEAPs
trade a few contracts a day, so the veto as written excludes almost every one.

## Decision

The user chose to replace the volume veto with a stricter open-interest floor.

- `engine.gates.volume_gate` always passes. It reports the median when one is supplied, or that
  it's unavailable, and its reason says it's informational. `option_vetoes.median_daily_volume_20d_is_veto: true`
  restores the v7 rule.
- `option_vetoes.open_interest_min` goes from 250 (ADR 0021) back to v7's 500.
- `option_implementation_score`'s hard checks are DTE, spread and open interest: 10 when all three
  pass, 3 less per failure. Its +2 deep-open-interest bonus now needs 1,000.
- daily-screen passes `median_20d_volume=None` and never estimates volume.

## Rationale

The position is one or two contracts held for months. What protects the exit is how many contracts
are open and how tight the live quote is, and both are measured live from Robinhood. Daily volume
on a LEAP mostly measures how often anyone happens to trade it. The 6% spread ceiling, 60-second
quote age, marketable-fill estimate, IV-outlier check and fair-value bound are all unchanged.

## Consequences

- MU's 2026-11-04 read (open interest 730, spread 3.71%) scores 10 and passes the sub-gate. Its
  80/80 total would have cleared §11.
- Names with open interest between 250 and 500 now fail where ADR 0021 let them through.
- A name with thin trading but deep open interest can clear. §12.3's exit haircuts and the
  §17 cap of 0.25% of NAV until calibration still bound what that can cost.
