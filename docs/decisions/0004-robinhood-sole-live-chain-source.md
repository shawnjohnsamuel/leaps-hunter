# ADR 0004: Robinhood MCP is the sole live-chain source; unverifiable liquidity = undeployable

**Status:** accepted (2026-07-08)

## Context
The liquidity hard disqualifiers (OI ≥50, bid/ask spread ≤5%, avg option volume ≥100)
require live per-contract data. Direct testing established the actual capabilities:
Robinhood MCP (read-only) returns live chains with real Greeks, OI, and spreads; the
Massive Market Data plan tier returns contract reference data and historical daily OHLC
but **no** live Greeks/IV/OI/spread (403 on those endpoints); web search is unreliable for
live or historical chain pricing. Neither parent framework named any data source at all.

## Decision
- **Robinhood MCP** (read-only tools only) is the single source of truth for live chain
  structure and liquidity gating.
- If a candidate isn't optioned on Robinhood, or its chain comes back thin/stale, liquidity
  is **unverifiable and the trade is undeployable** — logged to the watchlist, never
  estimated from web sources.
- **Massive** serves as the historical/backtesting layer for contracts already surfaced.
- **Web search** is limited to macro, fundamentals, news, and positioning research.
- Every daily report stamps which sources answered.

## Rationale
A liquidity gate fed by guessed numbers is worse than no gate — it launders uncertainty
into false confidence. Honest degradation (a DEGRADED report that refuses to issue
deployable verdicts when the connector is down) beats silent fallback.

## Consequences
Robinhood MCP is a deliberate single point of failure. The mitigation is honesty, not
redundancy. The read-only constraint is enumerated in the v6 spec itself: order placement,
review, and cancellation tools are denylisted by name and never called, regardless of how
a request is phrased.
