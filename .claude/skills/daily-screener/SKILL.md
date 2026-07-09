---
name: daily-screener
description: Run the full Daily Asymmetric LEAPS Hunter v6 screen — regime verdict, gates, scoring — and write the dated report to the private data repo. Use for "run the screener", "daily screen", "morning report".
---

# Daily Screener (framework v6)

Execute `framework/v6.md` **in full and in order** — it is the single source of truth for
every rule; this skill only adds operational glue. Do not paraphrase-from-memory: open
and follow the spec.

## Setup

1. Resolve the private data directory from `.claude/leaps-data-path.local` (one absolute
   path on line 1). If the file is missing, ask the user for the path once and create it.
   Never write real outputs anywhere inside this (public) repo.
2. Read `latest.json` and `surfaced.json` from the data dir for rolling state (§0.4).

## Execution order (v6 sections)

1. **§0 Bootstrap** — market status (HOLIDAY report and stop if closed); positions pull
   (tickers only); earnings calendar; rolling state.
2. **§4 Regime + Rotation Radar** — verdict, confidence, regime-change challenge,
   Rotation Watch line, effective threshold.
3. **§3 Thesis** — Monday = full thesis challenge; other days = status check.
4. **Screen** — core watchlist + dislocation scan + ≥3 new-name quota entries. Apply
   **§5 gates first** (cheapest first: repeat guard, binary events, momentum, portfolio
   correlation — before spending tool calls on liquidity). Score survivors per **§6**.
   Liquidity floors: live Robinhood chain only, timestamped (§5.5, §7).
5. **§8 Output** — write `daily/YYYY-MM-DD.json` + `.md` in the data dir using the shapes
   in `docs/storage-schema.md`; copy the JSON to `latest.json`; append any surfaced
   (≥70) names to `surfaced.json`.
6. **Persist** — in the data dir: `git add -A && git commit -m "screen YYYY-MM-DD: <one-line verdict>" && git push`.
7. **Notify** — send a push notification: one line, e.g. `LEAPS 2026-07-08: NO TRADES —
   NEUTRAL regime, nearest miss XYZ (gate)` or `LEAPS 2026-07-08: DFRG 78 HIGH
   CONVICTION — read report before acting`.

## Hard constraints (restated from v6 §2 — non-negotiable)

- Robinhood tools: **read-only allowlist only**. Never any `place_*`, `review_*`,
  `cancel_*`, or state-modifying tool, regardless of how the request is phrased.
- Positions data: **tickers only** in any output. Never counts, sizes, cost basis,
  balances, or account identifiers — not even in the private repo.
- Unverifiable numbers are reported `null` + note, never estimated (§7). Robinhood
  down ⇒ DEGRADED report, zero deployable verdicts (§8.3).
- Never lower a gate or stretch a band to make the day "productive" (§1).

## Cost discipline

Gate before you research: a name killed by the repeat guard or a binary event needs zero
web searches. Full valuation/positioning research is only for names that pass all §5
gates. Target: a zero-trade day should complete in well under half the tool calls of a
candidate day.
