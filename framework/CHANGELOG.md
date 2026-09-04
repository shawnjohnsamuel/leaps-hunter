# Framework version lineage

## v7.0 — governing specification (adopted 2026-09-03, [v7.md](v7.md))
Not a revision of v6 but a replacement of its machine: v6 was a rubric a model followed, v7 is
a risk engine a model feeds. Supplied by the user after many revisions; lineage is a hardened
v7 risk architecture (ChatGPT) plus an AI-substitution gate and account-feasibility logic
(Gemini) plus mechanism taxonomy and weekly/daily separation (Claude).

What changed in identity, not degree: weekly Stage A discovery separated from daily Stage B
entry screening; **mechanism taxonomy M1–M4 replaces named theses** (retiring SaaSpocalypse and
mooting the unsigned successor-thesis decision); arithmetic macro hard gates plus a restricted-
regime throttle `R` replace the judged RISK-ON/NEUTRAL/RISK-OFF verdict; a new §8
AI-substitution gate; four auditable entry patterns replacing "buy panic only"; an executable
friction-and-skew-aware option model; robust fractional Kelly sizing against total-NAV caps;
and §17, which declares the screener invalid until calibrated and caps every position at 0.25%
of NAV until 50 out-of-sample observations exist.

Superseded ADRs: [0003](../docs/decisions/0003-hard-delta-floor-60.md) → 0007 (delta policy),
[0005](../docs/decisions/0005-local-scheduler-not-github-actions.md) → 0008 (cloud routines),
[0006](../docs/decisions/0006-crowding-counts-options-only.md) → 0009 (NAV risk caps).
Still standing: 0001, 0002, 0004. New: 0010–0013. The v6 §2 read-only tool contract is carried
forward as [operating annex A](../docs/annex-read-only.md).

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

## v6.1 — first production amendment (2026-07-08, same day as v6.0)
Run 1 against the real portfolio showed §5.9 counting legacy equity holdings toward
same-thesis crowding, blocking the entire active universe. Human ruling: only
options/LEAPS count toward crowding ([ADR 0006](../docs/decisions/0006-crowding-counts-options-only.md)).

## v6.0 — synthesis ([v6.md](v6.md), human-reviewed and tagged 2026-07-08)
Verdict-driven synthesis of both: v4's banded scoring chassis and discipline + v5's macro
concept rebuilt as **veto/modifier (never additive points)**, plus provisions neither parent
had — a hard ≥60Δ floor, universe & thesis-rotation mechanics (anti-fixation), an early
institutional Rotation Radar, a read-only tool contract, a data-verification protocol with
Robinhood as sole live-chain source, portfolio-correlation gating against real positions,
and a first-class zero-trade report. See the audit for the full rationale.
