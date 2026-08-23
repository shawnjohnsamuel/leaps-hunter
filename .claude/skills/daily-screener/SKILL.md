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
2. Read `latest.json`, `surfaced.json`, and `watchlist-meta.json` from the data dir for
   rolling state (§0.4). Create `watchlist-meta.json` on first run (see Cost discipline).

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

## Cost discipline (binding — these are rules, not suggestions)

**Run this skill in a fresh session or a scheduled/cloud run — never inside a long
working conversation.** The screening work is a minority of the real cost; re-paying for
a large conversation history on every turn is the majority. This is the single biggest
lever.

**Tool budget, cheapest-first.** Gate before you research: a name killed by the repeat
guard, a binary event, momentum, or portfolio correlation needs zero further calls.

| Need | Use | Never |
|---|---|---|
| Prices, % moves, bid/ask | `get_equity_quotes` (lean; batch up to ~20) | — |
| 52-wk range, market cap, P/E | metadata cache (below), else `get_equity_fundamentals` | Calling fundamentals on the whole watchlist — it returns a full company biography per symbol (CEO, employee count, description) |
| Earnings dates | per-ticker checks on the specific names being screened | `get_earnings_calendar` with a broad/market-wide filter — one such call returned 56K+ characters and had to be spilled to a file |
| Chain structure | `get_option_chains` (expirations only) | Pulling contracts before a name reaches the structure stage |
| OI / spread / Greeks | `get_option_quotes` on a handful of candidate strikes | Whole-chain contract sweeps |

**Metadata cache.** Slow-moving fields — 52-week high/low and their dates, market cap,
sector, GAAP P/E, average volume — live in `watchlist-meta.json` in the data dir with a
`refreshed` date. Read from it; refresh only entries older than 7 calendar days, or when
a name's price moves outside its cached 52-week range. Prices and % moves are always live.

**Report shape.** The markdown is the human artifact and carries the prose. The JSON
carries data: keep `note` fields to one or two sentences, put extended reasoning in the
`.md` only. Do not duplicate long narrative across both files.

**Targets.** A zero-trade day should finish in roughly 10–15 tool calls; a candidate day
in 20–25. If a zero-trade run exceeds ~20 calls, something was researched before it was
gated — say so in `operational_notes`.

**Cheap alternative.** For a single ticker or a "what about X" question, use `quick-eval`
instead of this skill — it reuses cached context and runs the five never-skip gates only.
