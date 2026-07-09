# Framework version lineage

## v1–v3 (claude.ai chat era, not preserved)
Early iterations developed conversationally while evaluating real candidates (DVN, RKLB,
SOFI, NBIS). Their surviving lessons are baked into v4's "What This Screener Learned"
section and carried forward into v6's Lessons Ledger.

## v4 — production incumbent ([v4.md](v4.md))
Developed with Claude; run daily in production. 100-point banded scoring (Entry Timing 25 /
Catalysts 20 / Valuation 20 / Positioning 20 / Structure 15), hard disqualifiers, deep-ITM
survivability doctrine ("THE DVN LESSON"). Known blind spots (per audit): no macro regime
awareness at all, positioning/valuation bands calibrated for value/energy rather than
large-cap software, no hard delta floor, no zero-trade output format.

## v5 — independent challenger ([v5.md](v5.md))
Developed in parallel with ChatGPT; never production-tested. Added a macro regime layer
(its one genuinely important contribution) plus IV/options-market awareness — but as
additive scoring on a 110-point scale with a brittle mandatory-data rule, and it re-opened
the documented OTM failure mode ("risk-on → Allow: ATM / Moderate OTM"). Audited head-to-head
against v4 in [docs/audit-v4-vs-v5.md](../docs/audit-v4-vs-v5.md).

## v6 — synthesis ([v6.md](v6.md), drafted — pending human review before tag `v6.0`)
Verdict-driven synthesis of both: v4's banded scoring chassis and discipline + v5's macro
concept rebuilt as **veto/modifier (never additive points)**, plus provisions neither parent
had — a hard ≥60Δ floor, universe & thesis-rotation mechanics (anti-fixation), an early
institutional Rotation Radar, a read-only tool contract, a data-verification protocol with
Robinhood as sole live-chain source, portfolio-correlation gating against real positions,
and a first-class zero-trade report. See the audit for the full rationale.
