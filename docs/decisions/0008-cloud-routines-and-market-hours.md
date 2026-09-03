# ADR 0008: Cloud routines are the execution surface; the daily run is intraday

**Status:** accepted (2026-09-03) · **Supersedes:** [ADR 0005](0005-local-scheduler-not-github-actions.md)

## Context
ADR 0005 put the daily run on the Claude desktop scheduler because the Robinhood connector's
authentication lived in the desktop/claude.ai connector configuration and was assumed
unreachable from anything else. The cost was a hard laptop dependency: the Mac had to be awake
with the app running, and the screener missed a 19-trading-day stretch in July because of it.

Phase 0 tested the assumption instead of inheriting it. A one-time cloud routine reached
Robinhood with no laptop involved, and **connectors auto-attach** — the routine was created
without specifying `mcp_connections` and the server populated them, Robinhood included. NAV and
position inventory were retrievable there, which v7 §0 makes a hard precondition.

## Decision
- Both runs are **cloud routines**: Stage A weekly (Sunday), Stage B each trading day.
- The daily run fires **during market hours, ~10:15 ET** — not pre-market.
- No brokerage credential is ever duplicated into a third-party secret store; the routine
  inherits the account's connectors.

## Rationale
The intraday timing is forced by the spec, not preference. §12.1 requires a quote age ≤ 60
seconds and §0 makes live chain data a hard precondition, so a pre-market run would output
`NO TRADE — DATA INSUFFICIENT` every single day. Production data agrees: run 2 recorded INTU's
Jan-2028 $220 call at a 3.7% spread on the close against 7.8% intraday — off-hours quotes are
artifacts in both directions. 10:15 ET clears the opening auction before spreads are read.

## Consequences
- The laptop dependency is gone, and with it ADR 0005's principal failure mode.
- **Massive Market Data is absent from cloud routines** (it is not a claude.ai connector, and
  Claude Code-configured MCP servers cannot attach). The cloud path runs on Robinhood + HTTPS
  sources; breadth and the §17 option backtest become desktop-cadence jobs writing cached
  state. See [ADR 0011](0011-https-over-mcp-and-macro-sources.md).
- The heartbeat rule survives the move: the notification is the signal that the run happened,
  and its absence is the alarm. HOLIDAY files still make a missing file unambiguous.
- Run transcripts contain raw tool results, including account identifiers. Prompt-level privacy
  rules constrain what an agent *writes*, not what the platform logs — the boundary that
  matters remains the sanitizer allowlist and what is committed to the repos.
