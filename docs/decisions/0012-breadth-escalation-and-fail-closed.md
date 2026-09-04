# ADR 0012: Breadth is an escalation input, and unknown breadth fails closed

**Status:** accepted (2026-09-03) · **Amends v7 §6.1** — requires a §21 entry

## Context
v7 §6.1's equity-deleveraging gate ANDs three conditions: VIX ≥ 32 for two closes, S&P 500
≥10% below its 200-DMA, and NYSE breadth < 35% above its 200-DMA.

No free API publishes that breadth figure. The available sources are websites, not endpoints.
Left unresolved this is not a missing nice-to-have — because the conditions are AND-ed, an
unobtainable third term means **the gate can never fire**, silently converting a systemic-risk
stop into a no-op. That is the most dangerous possible failure for a gate whose entire purpose
is to stop trading in a deleveraging market.

## Decision
Two changes, both amendments to §6.1 as written:

1. **Breadth is an escalation input, not a daily one.** The other two conditions are keyless
   from FRED (`VIXCLS`, `SP500`) and cloud-reachable. The daily routine evaluates those two
   itself and consults breadth **only when both are already TRUE** — a rare, high-stress state.
2. **Unknown breadth fails closed.** When both other conditions hold and breadth cannot be
   read, the gate is treated as **ACTIVE**, not inactive.

Breadth itself is computed on the desktop from Massive's grouped-daily endpoint (12,541 US
tickers in a single call; a ~200-session bootstrap then one call per day) into
`state/breadth.json`, which the routine reads as cached state. The universe is all US common
stocks rather than NYSE specifically — recorded as an `[ASSUMPTION]` per §2.

## Rationale
Escalation gating dissolves the cloud/desktop split as a practical problem: the input that
cannot be fetched in the cloud is also the input that is almost never needed there. Fail-closed
is the only defensible default for a systemic gate — the cost of a false ACTIVE is a day of not
initiating new positions, which §0 already calls a successful session; the cost of a false
inactive is initiating long LEAPS into a deleveraging tape.

## Consequences
- The gate becomes strictly more conservative than v7 as written, never less.
- A stale `state/breadth.json` degrades to fail-closed rather than to a wrong answer.
- Both deviations — the fail-closed rule and the all-US-stocks universe — must appear in §21's
  change log and be surfaced in any report where the gate's status depends on them.
