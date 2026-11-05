# ADR 0024: Read the January LEAP expiry as well as the nearest one

**Status:** accepted (2026-11-05) · **Amends:** daily-screen's §11 preliminary chain read and §12
chain pull · **Relates to:** [ADR 0023](0023-volume-note-and-open-interest-500.md)

## Context

daily-screen read one expiration per name: the nearest in §12.1's 365–900 DTE range. Through
late 2026 that was December 2027. LEAP open interest concentrates in the January contracts, so
the read often found an empty strike while the next month's was active. Since ADR 0023, open
interest (minimum 500) is the main liquidity test, which makes this matter more.

On 2026-11-05, at the same delta-band strikes:

| Name | Dec 2027 OI | Jan 2028 OI | Jan 2028 spread |
|---|---|---|---|
| Zscaler $150C | 0 | 462 | 5.2% |
| Vertiv $130C | 0 | 84 | 4.3% |
| GE Vernova $600C | 8 | 68 | 2.6% |
| Eaton $260C | 0 | 29 | 4.4% |

On 2026-11-04 Micron's Dec 2027 call had 730 open against 1,172 for a Jan 2028 call.

The user considered lowering the floor to 250 instead and chose this.

## Decision

- `engine.gates.leap_expirations_to_check(expirations, today, cfg)` returns the nearest
  expiration in `option_vetoes.dte_range`, plus the first January one in range when that is a
  different date.
- daily-screen reads the delta-band strike at each. `engine.gates.deepest_open_interest` keeps
  the one with more open interest (a tie goes to the earlier date), and the rest of that name's
  screen (§12 pricing, §13 structure, §14 sizing, the ledger entry) uses the kept expiration.
- No threshold changes. Every §12.1 veto applies to the kept contract unchanged.

## Consequences

- Up to one extra quote call per name that reaches §11, using the same Robinhood tools.
- A January contract can sit up to about five weeks further out than a December one. That is
  slightly more time value per contract, priced by the same §12 model, and well inside the
  900-day limit.
- On 2026-11-05 this would not have changed a verdict. Those names scored 66–73, under the
  restricted threshold of 80, and Zscaler's 462 is still under 500. It changes which contract a
  future clear is measured on.
