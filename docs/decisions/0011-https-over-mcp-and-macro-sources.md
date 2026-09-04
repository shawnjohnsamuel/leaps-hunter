# ADR 0011: Prefer HTTPS over MCP on the daily path; FRED is the macro source of record

**Status:** accepted (2026-09-03) · **Does not affect:** [ADR 0004](0004-robinhood-sole-live-chain-source.md)
· **Amended by:** [ADR 0014](0014-macro-fetch-desktop-only.md) (2026-09-04) — this ADR's claim
that HTTPS calls "behave identically on the desktop and in the cloud" is **wrong**: FRED, Alpha
Vantage, multpl.com, and direct SEC EDGAR are all unreachable from a cloud routine's sandbox.
The source/series selections below remain correct; only the cloud-reachability assumption is
amended. These fetches are now desktop-only (`macro-refresh` skill).

## Context
Phase 0 established that MCP connectors do not reliably reach cloud routines. Massive Market
Data is absent there because it is not a claude.ai connector, and Claude Code-configured MCP
servers cannot be attached to a routine. A plain HTTPS endpoint called from `Bash`/`urllib`
behaves identically on the desktop and in the cloud.

Separately, v7 §6 names macro series that Massive either lacks or serves too coarsely — its
inflation-expectations series is monthly, and §6.1 needs a 10-day change in the 5y5y breakeven.

## Decision
**Prefer a keyless or keyed HTTPS endpoint over an MCP connector for every input on the daily
path.** MCP is reserved for what has no public HTTP equivalent. Specifically:

| Input | Source | Auth |
|---|---|---|
| §6.1/§6.2 macro series, risk-free rate | FRED `fredgraph.csv` | none |
| §6.2 CAPE percentile | multpl.com (Shiller series, 1871→) | none |
| §10 NTM estimate revisions | Alpha Vantage `EARNINGS_ESTIMATES` | free key |
| §8 retention / RPO / fundamentals | SEC EDGAR XBRL | none (UA required) |
| Live chain, Greeks, IV, OI, NAV, positions | **Robinhood MCP** | connector |
| Breadth, historical option OHLC | Massive (desktop cadence) | connector |

Two series decisions inside FRED:
- §6.1's **absolute** credit gate keeps `BAMLH0A0HYM2`. FRED caps ICE BofA series at ~3 years
  on every path — **confirmed with an authenticated key on 2026-09-03: the keyed JSON API
  returns the same 795 observations as the anonymous CSV, so this is ICE licensing and not an
  auth limit.** Three years is ample for a current level and a 20-day change.
- §6.2's **percentile** component uses `BAA10Y` (10,167 observations back to 1986). Recorded as
  an `[ASSUMPTION]` per §2 with a §21 entry: investment-grade is defensible as a percentile
  input, not as a level input.

## Rationale
The alternative — routing everything through MCP — makes the cloud path depend on which
connectors happen to propagate, a property this project does not control and cannot test
except empirically. HTTPS is testable, portable, and free here.

## Consequences
- **ADR 0004 is untouched.** Robinhood remains the sole live-chain source; Massive's option
  endpoints still 403. Robinhood also remains a deliberate single point of failure.
- Massive is demoted from a screening dependency to a desktop enrichment layer. Nothing on the
  daily cloud path may require it.
- Two free API keys are needed (Alpha Vantage required, FRED optional). Neither belongs in
  `mcp_connections`; both reach the routine as environment variables or a mounted secret, and
  neither is committed.
- A source that starts requiring payment or a login is a §21 event: record it, and degrade the
  affected rule honestly per §3 rather than substituting an unnamed source.
