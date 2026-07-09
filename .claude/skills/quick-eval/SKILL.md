---
name: quick-eval
description: Fast gate-check of a ticker, tweet, or headline against today's cached LEAPS Hunter context — a 2-minute read, NOT a full v6 screen. Use when the user drops a ticker/quote/link and wants a quick take.
---

# Quick Eval — fast read, honestly labeled

Give a fast, cheap read by **reusing today's completed research** and running only the
never-skip gates. This is explicitly NOT a full v6 screen and must never present itself
as one.

## Input

One of: a bare ticker · pasted text (tweet/headline/snippet — extract ticker(s); if none
extractable, say so and stop) · optional trailing question. Multiple tickers: evaluate
each briefly or ask which one if >3.

## Cache policy

Resolve the data dir from `.claude/leaps-data-path.local`, read `latest.json`:

- Dated **today (trading day)** → reuse regime verdict, Rotation Watch, correlation set,
  and any per-ticker research as-is. If markets have clearly moved hard intraday (one
  VIX/index quote check), keep the regime but flag "morning regime; market has moved."
- Dated a **prior trading day** → banner the output **STALE CONTEXT**, treat the regime
  as low-confidence, reuse nothing per-ticker.
- Missing/unreadable → say so; run gates cold; suggest a full screen.

## Never-skip gates (cheap, always run — even on cold tickers)

1. **Binary events:** earnings within 14 days (`get_earnings_calendar`).
2. **Momentum/chasing:** 30-day move + distance from 52-week high (`get_equity_historicals`).
3. **Liquidity floor:** live LEAPS chain on the target expiry — OI ≥50, spread ≤5%
   (`get_option_chains` → `get_option_quotes`). Unverifiable = say so, never estimate.
4. **Macro mismatch** vs. cached regime verdict.
5. **Portfolio overlap** vs. cached correlation set (tickers only).

Skip/abbreviate everything else: catalyst research, 13F digging, valuation bands,
scenario analysis, structure optimization.

## Cold-ticker budget

A ticker absent from today's research gets **max ~8 tool calls** (quote, historicals,
earnings date, chain snapshot, 1–2 web searches for "why is it moving"). If gates pass
and the story smells like genuine panic-dislocation, the verdict is WORTH A FULL SCREEN —
never a score. If the budget runs out inconclusive, say so and suggest the full screen.

## Output contract

Always headed:
`⚡ QUICK READ — cached context from <date/time> — NOT a full v6 screen`
(+ `— STALE CONTEXT` banner when applicable)

Verdict vocabulary — deliberately disjoint from v6 tiers, never a /100 score, never the
words "High Conviction" or "Elite":

- **REJECT — [gate]:** failed a hard disqualifier; name it and stop.
- **NOT COMPELLING:** passes gates but nothing suggests elite asymmetry (no drawdown,
  crowded, thesis-incoherent) — one paragraph why.
- **WORTH A FULL SCREEN:** passes gates + genuine dislocation signature; list the 2–3
  things a full screen must verify.

Read-only constraint applies in full (v6 §2): never any order tool, any phrasing.
