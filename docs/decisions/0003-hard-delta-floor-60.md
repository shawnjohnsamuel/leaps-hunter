# ADR 0003: Hard delta floor at ≥60Δ (auto-reject below)

**Status:** accepted (2026-07-08)

## Context
The framework's identity is deep-ITM survivability ("THE DVN LESSON"), yet neither parent
enforced it: v4 merely scored <40Δ structures at 7/15 — nothing auto-rejected them — and v5
explicitly permitted "ATM / Moderate OTM / Higher convexity" in risk-on regimes. A competing
version historically produced OTM strikes that violated the framework's own intent; both
parents leave that door open.

## Decision
v6 adds a hard disqualifier: any recommended structure below **60 delta** is auto-rejected,
regardless of score or regime. Within the legal range, v4's delta bands still apply
(70–80Δ scores highest; 60–70Δ is legal but non-max-scoring).

## Rationale
A rule that matters only when it's inconvenient must be a gate, not a score. 60Δ preserves
the deep-ITM identity while keeping v4's "balanced" 60–70Δ band available; a documented
failure mode gets closed structurally instead of by vigilance.

## Consequences
No regime, IV environment, or conviction level can authorize a sub-60Δ recommendation.
v5's IV-aware structure logic survives, but only *above* the floor (e.g., high IV → deeper
ITM or debit spreads; low IV never unlocks OTM).
