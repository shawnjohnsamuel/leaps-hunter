# ADR 0005: Daily automation runs on the Claude desktop scheduler, not GitHub Actions

**Status:** ~~accepted (2026-07-08)~~ — **SUPERSEDED by [ADR 0008](0008-cloud-routines-and-market-hours.md)** on
2026-09-03 during the v7 migration: cloud routines reach the connectors; the laptop dependency is retired. Retained as design history; the reasoning
below explains why the rule existed, which the superseding ADR builds on.

## Context
The daily screener must run unattended each weekday morning and needs the Robinhood MCP
connector for live-chain gating. That connector's authentication lives in the Claude
desktop/claude.ai connector configuration — it is not reachable from the raw Anthropic API.
A GitHub Actions cron job calling the API directly would therefore require re-provisioning
brokerage-adjacent OAuth credentials as GitHub secrets: fragile, and it moves exactly the
material the public/private boundary exists to protect.

## Decision
The daily run is a **scheduled task in the Claude Code desktop app** (weekdays, 7:30 AM ET),
which executes in the same environment as interactive sessions and inherits the connectors.
It writes the dated report to the private data repo and sends a push notification with a
one-line verdict.

## Rationale
The screener's hard constraint is "a Claude session with the user's connectors must be the
thing that runs." Only the desktop scheduler (or, if verified, Claude cloud routines)
satisfies that without duplicating brokerage credentials into third-party secret stores.

## Consequences
- The Mac must be awake with the app running at fire time; a missed run produces **no dated
  file**, which the dashboard surfaces as a prominent STALE banner — and runs are written
  even on market holidays (as HOLIDAY reports), so a missing file always means failure.
- The morning push notification is the heartbeat; its absence is the alarm.
- GitHub Actions remains fine for connector-free jobs (e.g., deploying the demo site).
