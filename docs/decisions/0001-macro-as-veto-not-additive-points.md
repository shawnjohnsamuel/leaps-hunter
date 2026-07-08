# ADR 0001: Macro regime acts as veto + modifier, never additive points

**Status:** accepted (2026-07-08)

## Context
v4 had no macro awareness at all — a real blind spot for 12–24-month duration assets whose
multiples are driven by rates and liquidity. v5 introduced a macro layer three ways at once:
a hard "Macro Mismatch" disqualifier, an additive 0–10 Macro Compatibility score (making its
scale /110), and a Strong/Neutral/Weak label.

## Decision
v6 keeps macro as a **gate and a modifier only**: a compact daily regime verdict
(Risk-on / Neutral / Risk-off / Stressed) that (a) hard-rejects macro-mismatched trades,
(b) constrains allowed option structure, and (c) may *raise* the deployment threshold in
hostile regimes. It contributes **zero points** to the 100-point score.

## Rationale
Additive macro points inflate scores precisely when the regime feels good — pushing mediocre
setups over the display threshold during euphoria, which is exactly when this framework's
discipline matters most. If macro conflicts, the trade is already dead at the gate; if it
doesn't, regime beta is not trade quality. Keeping the scale at /100 also preserves
comparability with v4's production history.

## Consequences
Macro can only ever make the screen *stricter*, never more generous. v5's mandatory
kitchen-sink data collection ("failure … INVALIDATES the screen") is replaced by a small,
actually-obtainable indicator set; missing indicators degrade the verdict's stated
confidence instead of invalidating the run.
