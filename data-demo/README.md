# data-demo — synthetic sample days

**Everything here is fabricated.** Tickers (DFRG, NMBS, VLTC…) are fictional companies,
prices and scores are invented, and no file reflects any real screen, position, or
recommendation. This directory holds private-shaped example input for the sanitizer
pipeline (`scripts/sanitize.py`) — running one of these through it produces a synthetic
public artifact, which is how the four v7 files below were verified to sanitize cleanly
(no `account_ref`/`nav_at_run` leakage) during Phase 7.

**v6.1 days** (four, July 2026) cover the old report-type surface:

| File | Type | Demonstrates |
|---|---|---|
| `daily/2026-07-02.*` | CANDIDATE | a HIGH CONVICTION surfaced trade with full scoring |
| `daily/2026-07-03.*` | HOLIDAY | market closed (July 4 observed) — absence-is-failure design |
| `daily/2026-07-06.*` | ZERO_TRADE | the modal day, incl. Monday thesis challenge |
| `daily/2026-07-07.*` | DEGRADED | Robinhood unreachable → no deployable verdicts |

**v7 days** (four, October 2026) cover v7's result surface (`framework_version: "7.0"`):

| File | Result | Demonstrates |
|---|---|---|
| `daily/2026-10-06.json` | NO_TRADE | the modal day — a real near-miss (NMBS, 4 points short) among the rejections |
| `daily/2026-10-12.json` | HOLIDAY | market closed |
| `daily/2026-10-13.json` | DATA_INSUFFICIENT | S0's live-chain precondition failed — fail-closed, not a guess |
| `daily/2026-10-14.json` | CANDIDATE | a fictional full clear through S15 — as of 2026-09-04 (this repo's real timeline) no real candidate has ever cleared, so this is the only place the CANDIDATE rendering path is exercised |

Plus `latest.json` (copy of the newest v6.1 day) and `surfaced.json` (v6.1's repeat-guard
history — v7 has no equivalent concept), matching the shapes in
[docs/storage-schema.md](../docs/storage-schema.md) (v6.1) and
[docs/storage-schema-v7.md](../docs/storage-schema-v7.md) (v7).
