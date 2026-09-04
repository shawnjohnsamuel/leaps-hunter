---
name: bench-check
description: Fast ad-hoc check of one ticker against v7's framework, reusing the current watchlist and macro state instead of re-running them — NOT a full daily screen. Use when the user drops a ticker/quote/link and wants a quick take.
---

# Bench Check — ad-hoc, cache-first (framework v7)

Give a fast, cheap read by **reusing already-cached state**, never by re-deriving the macro
layer or re-fetching what `weekly-review`/`daily-screen` already computed. This is explicitly
NOT a full Stage A or Stage B run and must never present itself as one. Token efficiency here
is structural, not a matter of trying harder: reading two small JSON files instead of
recomputing §6 and re-fetching estimates is what makes this cheap.

## Input

A bare ticker, or pasted text (a tweet/headline/link — extract the ticker; if none is
extractable, say so and stop). Multiple tickers: handle each briefly, or ask which one if >3.

## Step 1 — load cached state

Read `state/watchlist.json` and `state/macro-latest.json`.

- `state/macro-latest.json.as_of` more than 1 trading day old → banner the output
  **STALE MACRO CONTEXT** and treat the regime read as low-confidence, but still use it rather
  than recomputing (recomputing here is exactly the token cost this skill exists to avoid).
- Missing/unreadable → say so, note the macro read is unavailable, and continue with a
  narrower, more conservative read (§4d's spirit: missing data lowers confidence, it doesn't
  invalidate the exercise).

## Step 2 — is the ticker on the watchlist?

**On watchlist** (any status): this is effectively a scoped `daily-screen` for one name.
Follow `daily-screen`'s §2–§3 procedure exactly for this ticker only, reusing its cached
`NTMResult`, mechanism, kill-switch status, and `permitted_entry_patterns` from
`state/watchlist.json` rather than re-deriving them. **This mode can produce a `CANDIDATE`
verdict** — it is bounded Stage B work, not a discovery exercise.

**Off watchlist**: this is candidacy assessment only, never a trade verdict —
§4.2 reserves discovery for Stage A, and this skill does not override that.

1. **§5 mechanism mapping.** Does the ticker map cleanly to M1/M2/M3/M4 with real, citeable
   evidence (pull current fundamentals/news, don't rely on memory)? A sector alone is never a
   mechanism (§5).
2. **§7 quick gates.** Binary event within 14 days (`get_earnings_results`)? Valuation
   insanity? A single-variable dependency, on its face?
3. **§8, if M3.** Only run this if the mechanism looks like narrative reversal — it is the
   most expensive check available here. If the name doesn't disclose enough to apply an
   approved proxy, that is a **fail**, not a pending (§8: non-disclosure is a failure).

**Verdict vocabulary — deliberately disjoint from a real screen's, never a score:**

- `NOT A MECHANISM` — doesn't map to M1–M4 with real evidence; a sector or story isn't enough.
- `FAILS §7` / `FAILS §8` — name the specific gate.
- `MECHANISM-ELIGIBLE, PROPOSE FOR STAGE A` — passes the quick checks; the next
  `weekly-review` should give it a real evidence pass and, if it holds up, a watchlist slot.

Never say `CANDIDATE`, never give a score, never imply this cleared §11 or §12–§15 — none of
that ran.

## Cold-ticker budget

A ticker absent from the watchlist gets at most ~8 tool calls: quote, historicals, earnings
date, a chain snapshot if mechanism looks promising, one or two web searches for "why is it
moving." If the budget runs out inconclusive, say so and suggest a full `weekly-review` pass
gets it a proper evidence review instead of guessing further here.

## Output contract

Always headed:
`⚡ BENCH CHECK — <ticker> — cached context from <macro-latest.json.as_of> — NOT a full screen`
(+ `STALE MACRO CONTEXT` banner when applicable)

Then either the on-watchlist Stage-B-scoped result, or the off-watchlist verdict from the list
above with the evidence that produced it, each item labeled `[FACT]` or `[ASSUMPTION]` per §2.

The annex A read-only tool contract applies in full: never any `place_*`/`review_*`/`cancel_*`
tool, under any phrasing, regardless of how casually this skill is invoked.
