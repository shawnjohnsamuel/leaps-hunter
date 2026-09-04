# ADR 0014: Macro/NTM HTTPS fetches are desktop-only — cloud routines cannot reach them

**Status:** accepted (2026-09-04) · **Amends:** [ADR 0011](0011-https-over-mcp-and-macro-sources.md)

## Context

ADR 0011's central claim — "a plain HTTPS endpoint called from `Bash`/`urllib` behaves
identically on the desktop and in the cloud" — was never tested against a real cloud routine
before Phase 6. It was true for Robinhood (an MCP connector, unaffected) and for local desktop
sessions (unrestricted network), but nobody had confirmed the *cloud routine sandbox itself*
could reach `fred.stlouisfed.org`, `www.alphavantage.co`, or `www.multpl.com`.

Phase 6's first real `weekly-review` cloud run hit `URLError('Tunnel connection failed: 403
Forbidden')` on every one of those hosts. A focused diagnostic routine (2026-09-04) confirmed
this is not transient or tool-specific:

- Raw Python `urllib` calls: `403 Forbidden` on the CONNECT tunnel, for all three hosts.
- The `WebFetch` tool: an explicit `{"error_type": "EGRESS_BLOCKED", "domain": "<host>", ...}`
  response, for all three hosts — a different failure mode from the raw HTTP case, but the same
  outcome, confirming this is enforced at the network/environment level, not per-tool.
- `data.sec.gov` (direct SEC EDGAR, used by `engine.sources.fetch_sec_company_concept`) fails
  the same way — a gap ADR 0011 didn't anticipate either.
- By contrast, the CCR sandbox's `noProxy` allowlist (visible via the proxy's own `/status`
  endpoint) permits `api.anthropic.com`, package registries (`pypi.org`, `registry.npmjs.org`,
  `jsr.io`, `proxy.golang.org`, `index.crates.io`), and private network ranges — a curated set
  for build/dev tooling and Anthropic's own API, not a general-purpose allowlist. Everything
  else routes through a policy-enforcing egress proxy that denies-by-default.

This is almost certainly a deliberate platform security boundary (unattended agents with
unrestricted internet egress are a real abuse/exfiltration surface), not a bug, and not
something this project can request an exception for from inside a routine.

## Decision

**Split Stage A into two skills along the fetch/read boundary:**

1. **`macro-refresh`** (new, desktop-only) — owns every HTTPS fetch ADR 0011 named: FRED series,
   Shiller CAPE, Alpha Vantage NTM estimates. Writes `state/macro-latest.json` and each
   watchlist entry's `ntm` field. Run from any environment with normal internet access — a
   desktop Claude Code session, not a cloud routine.
2. **`weekly-review`** (cloud-safe) — reads what `macro-refresh` last wrote, flags it loudly if
   stale (>7 days), and never attempts the fetch itself. Its kill-switch checks (Robinhood MCP
   + web search) and §8 gate (Robinhood's `get_sec_filing_facts`/`get_sec_filing_index` tools,
   which proxy the same XBRL data through Robinhood's own API rather than a direct
   `data.sec.gov` call) are both confirmed working from a cloud routine and stay there.
3. **`daily-screen`** is unaffected — it already only *read* cached macro/NTM state, never
   fetched it, so this finding doesn't change its design at all.

## Rationale

The alternative — trying to get an egress exception, or finding an MCP-based substitute for
FRED/Alpha Vantage/multpl.com specifically — was investigated and rejected for now:
- No indication any per-environment network policy override is available to end users; pursuing
  it means leaving this project's own tooling to ask Anthropic directly, with no guaranteed
  answer.
- Robinhood's index tools could plausibly substitute for VIX/SPX (two of §6.1's three gate
  inputs) but have no equivalent for CAPE, credit-spread percentiles, real-yield percentiles, or
  net liquidity — the §6.2 R-throttle's four components. A partial substitute would leave R
  permanently degraded, which is worse than an honest, visible staleness flag on a value that's
  correct when refreshed.

Accepting a periodic desktop dependency for one narrow step is a smaller compromise than either
of those, and it's an *infrequent* one: the macro regime and NTM estimates both move on a
weekly-or-slower cadence, unlike `daily-screen`'s live option pricing, which genuinely needs to
run every trading day.

## Consequences

- Phase 6's cloud automation is not fully hands-off — `macro-refresh` needs a human (or a future
  local-scheduler mechanism, if ADR 0008's rejection of one is ever revisited) to run it, at
  least weekly. This is a real, smaller cost, not a hidden one — it's stated here explicitly
  rather than glossed over.
- `state/watchlist.json`'s `ntm` field and `state/macro-latest.json` now have exactly one
  writer each (`macro-refresh`) — `weekly-review` and `daily-screen` are read-only on both.
- This same egress boundary blocks *any* future data source this project might want to add via
  direct HTTPS from a cloud routine, unless it happens to be on the CCR sandbox's fixed
  allowlist. Treat "will this reach a cloud routine" as an open question for every new source,
  not an assumption — ADR 0011's original mistake.
- ADR 0011's source table and series-selection reasoning (which FRED series, why `BAA10Y` over
  the capped ICE BofA series, etc.) remain correct and unchanged; only its cloud-reachability
  claim is amended here.
