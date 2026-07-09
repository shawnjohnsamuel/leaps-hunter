# data-demo — synthetic sample days

**Everything here is fabricated.** Tickers (DFRG, NMBS, VLTC…) are fictional companies,
prices and scores are invented, and no file reflects any real screen, position, or
recommendation. This directory exists so the public dashboard can demo every state the
system produces without exposing real output (see ADR 0002).

The four days cover the full report-type surface (v6 §8):

| File | Type | Demonstrates |
|---|---|---|
| `daily/2026-07-02.*` | CANDIDATE | a HIGH CONVICTION surfaced trade with full scoring |
| `daily/2026-07-03.*` | HOLIDAY | market closed (July 4 observed) — absence-is-failure design |
| `daily/2026-07-06.*` | ZERO_TRADE | the modal day, incl. Monday thesis challenge |
| `daily/2026-07-07.*` | DEGRADED | Robinhood unreachable → no deployable verdicts |

Plus `latest.json` (copy of the newest day) and `surfaced.json` (repeat-guard history),
matching the shapes in [docs/storage-schema.md](../docs/storage-schema.md).
