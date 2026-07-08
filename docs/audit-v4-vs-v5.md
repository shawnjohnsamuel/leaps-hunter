# Audit: Framework v4 (Claude) vs. v5 (ChatGPT)

> **What this is:** the head-to-head audit that preceded the v6 synthesis, preserved as
> design history. v4 ([framework/v4.md](../framework/v4.md)) was the production incumbent,
> developed with Claude and run daily against real market data. v5
> ([framework/v5.md](../framework/v5.md)) was independently developed with ChatGPT and never
> production-tested. Ground rule for the audit: neither incumbency nor recency counts as
> evidence — both versions are judged on their text. Conducted 2026-07-08 with Claude Code.
> The resulting v6 design decisions are recorded as ADRs in [decisions/](decisions/).


## 1.1 Structural comparison

| Dimension | V4 (Claude, production) | V5 (ChatGPT, untested) |
|---|---|---|
| Total scale | 100 pts (25/20/20/20/15) | **110 pts** — same five categories + Macro Alignment 0–10 (additive) |
| Macro regime | **Absent entirely** — no macro section anywhere | Mandatory daily macro collection (rates, curve, CPI/PCE, ISM, VIX, VVIX, skew, breadth, gamma) + Macro Mismatch hard disqualifier + additive 0–10 score |
| Gating architecture | Hard disqualifiers (auto-reject) → banded scoring → deploy tiers | Same architecture + 2 extra disqualifiers (macro mismatch, single-macro-factor dependency) |
| Scoring rubrics | **Concrete point bands with worked examples** (e.g., "Stock down 10–20% in 2–5 days on fixable issue = 25") | Qualitative prioritize/reward/punish lists — **no point bands at all** |
| Delta / structure | Explicit delta bands scored: 70–80Δ=15 … <40Δ=7; "THE DVN LESSON: Deep ITM survives 'correct but late'" | Regime-conditional: high-vol → deep ITM/spreads; **risk-on → "Allow: ATM / Moderate OTM / Higher convexity"**; no delta numbers anywhere |
| IV / options-market awareness | One line ("Call debit spread … High IV or expensive premium") | Dedicated section: VVIX, IV percentile, skew, term structure → structure choice |
| Liquidity floors | OI <50, spread >5%, volume <100 = reject | Identical |
| Duration rules | Identical mapping (6–12mo → Jan 2027 min, etc.) | Identical |
| Valuation disqualifier | >50x P/S unprofitable = reject **"(unless biotech with Phase 3 data)"** | Same, **without** the biotech carve-out; adds macro-adjusted valuation rules |
| Positioning rubric | Absolute ownership bands (5–15% = 20 pts; >60% = 5 pts) | Qualitative: 13F trends, insider buying, short interest, sentiment divergence |
| Deploy tiers | 85–100 aggressive / 75–84 conviction / 65–74 conservative / 50–64 pass-or-tiny / <50 reject | 95–110 aggressive / 85–94 high conviction / 75–84 moderate / 70–74 starter / <70 reject |
| Display threshold | "only show trades scoring 70+" — **contradicts** its own 65–74 "Deploy conservatively" tier | 70+ — consistent with its tiers |
| Output | Top 1–3, detailed template | Single trade, same template + macro context section + macro deterioration exit trigger |
| Empirical grounding | "What this screener learned" — DVN/RKLB/SOFI/NBIS production lessons baked in | None (never run against real money) |
| Zero-trade day defined | ❌ | ❌ |
| Data sources named | ❌ | ❌ (says "use web searches" — unreliable for chains, per your testing) |
| Portfolio correlation vs. real holdings | ❌ | ❌ |
| SaaS / universe definition | ❌ — **neither file mentions SaaS or any universe at all** | ❌ |

## 1.2 Dimension-by-dimension, argued

**Entry timing — V4 wins, clearly.** V4's banded table ("down 10–20% in 2–5 days on fixable issue = 25 … Up >30% recently or at ATH = **0**") is auditable and resists score inflation. V5's version ("Prioritize: Panic / Forced selling / Temporary narrative breaks… Punish: Euphoria") is the same philosophy with the numbers removed — a motivated screen can award 22/25 to any red candle. V5 adds nothing V4 lacks except macro-flavored examples ("Software selloffs from guidance conservatism"), which are prompt garnish, not rules. One V4 caveat: its example anchors (DVN, PLTR, NBIS) will age and should become generic archetypes in V6.

**Catalyst independence — near parity; V4 edges it.** Both require 2–3 independent catalysts with ≥1 company-controlled. V4's band table (3+ independent = 20 → all-same-macro = 5) plus the AMD-vs-DVN worked example is more operational. V5 contributes one genuinely good sentence V4 lacks: *"Macro-sensitive catalysts receive LOWER scores unless paired with company execution"* — an explicit discount rule worth keeping. V5 also elevates "Entire thesis depends on one macro factor = REJECT" to a hard disqualifier; V4 only rejects one-commodity/one-customer/one-product. For a rates-sensitive SaaS universe, V5's version is the right generalization.

**Valuation/quality — V4's structure, V5's substance.** V4 has bands with numbers; V5 has a list plus macro adjustments ("Higher rates → punish high-multiple unprofitable names; Tight credit → require stronger balance sheets") that are genuinely correct for 12–24-month duration assets and absent from V4. But **V4's bands are miscalibrated for your stated universe**: "Trading <12x earnings + profitable = 20 pts" describes value/energy names (its DVN heritage), not enterprise SaaS — quality SaaS in a panic still won't trade at 12x earnings, so V4 would systematically score your actual hunting ground 10–16/20. V6 needs V4-style bands **rebuilt for quality-growth** (EV/FCF vs. growth, Rule of 40, net cash, buyback capacity) with V5's rate-regime adjustment layered on. V4's biotech Phase-3 carve-out is a gameable exception irrelevant to your mandate; V5 correctly dropped it — follow V5.

**Positioning/sentiment — V5 conceptually better for large-caps; V4's format still right.** V4's absolute-ownership bands ("5–15% institutional = 20 pts, early to trend"; ">60% + retail saturated = 5") are a **misfit with the SaaSpocalypse mandate**: mega/large-cap software is 70–90% institutionally owned as a baseline, so V4 as written scores your entire universe "already discovered." Its bands were calibrated on the DVN/SOFI/NBIS era, not large-cap SaaS. V5's trend-based inputs (13F accumulation *trends*, insider buying, short interest, "sentiment divergence," "forgotten leaders") are the right lens for large-caps — but delivered as an ungameable-in-neither-direction vibes list ("CNBC consensus," "AI tourist flows"). V6: V4's banded format, rebuilt around **direction of institutional flow and sentiment vs. fundamentals divergence**, not absolute ownership levels.

**Structure/survivability & delta — V4 wins on discipline; V5 contributes IV-awareness; both share the delta-floor hole.** V4's scored delta bands and the DVN lesson encode your deep-ITM philosophy. V5's contribution is real: matching structure to the IV environment (high IV → spreads/deeper ITM; low IV → convexity) is correct options theory V4 handles in one throwaway line — and it matters, because panic entries by definition buy elevated IV. **But V5 also explicitly reopens your documented failure mode:** in "Strong Risk-On / Falling Yield Environments: **Allow: ATM / Moderate OTM / Higher convexity**" — the exact OTM drift a competing version already burned you with. And note: **neither version has a hard delta floor.** V4 merely scores <40Δ at 7/15 — nothing auto-rejects a 35Δ recommendation. For a framework whose identity is "deep-ITM survivability," the delta floor belongs in hard disqualifiers, not the scoring rubric. That's a V6 addition, from neither parent.

**Macro handling — V5's concept is its single biggest genuine contribution; its implementation is its single biggest flaw.**
- *The concept is right:* V4 has literally zero macro awareness. A framework buying 12–24-month duration assets with no view on rates/liquidity regime is missing the variable that most drives LEAPS multiple expansion/compression. V5's Macro Mismatch hard disqualifier ("Long-duration speculative tech during sharply rising yields = reject") and the "macro deterioration trigger" in time-based exits are both correct and worth keeping.
- *The implementation is wrong, three ways:*
  1. **Double/triple counting.** Macro appears as a hard disqualifier, AND an additive 0–10 score, AND a "Macro Alignment: Strong/Neutral/Weak" label. If macro conflicts, the trade is already dead at the gate; if it doesn't, the additive 10 points can push a mediocre 66-point setup over the 70 display threshold *precisely when the regime feels good* — score inflation exactly when euphoria discipline should be tightest. This is anti-correlated with the framework's own philosophy.
  2. **Brittle mandatory collection.** "Failure to include fresh macro and market data INVALIDATES the screen" attached to a kitchen-sink list (2Y/10Y/30Y, CPI, Core CPI, PCE, Core PCE, payrolls, both ISMs, retail sales, sentiment, VVIX, skew, term structure, "gamma positioning if available") — several of which are unreliable or unavailable via your actual tooling (you have no gamma positioning source; VVIX/skew are spotty via web search). Followed literally, most screens self-invalidate. Followed loosely, the rule is dead letter. Either way it's bad law.
  3. **Scale distortion.** The /110 total makes tiers non-comparable to V4's production history and the extra 10 points are pure regime beta, not trade quality.
- **Verdict for V6 (this is the Part 2 justification):** macro as **veto + modifier** — a compact regime verdict that (a) hard-rejects mismatched trades (V5's disqualifier, kept), (b) conditions allowed structure (V5's IV/regime→structure logic, kept), and (c) can *raise* the deployment threshold in hostile regimes — but **never adds points**. Additive macro loses on the merits, not by default.

**Hard disqualifiers — V5 slightly stronger set; V4 slightly cleaner statement.** Union in V6: V4's six categories + V5's macro mismatch + V5's single-macro-factor dependency, minus V4's biotech carve-out. Liquidity floors identical in both (OI ≥50, spread ≤5%, volume ≥100) and stay — with the V6-only addition that they can be verified **exclusively against Robinhood live chain data** (neither file names a data source; your Massive tier can't gate same-day liquidity).

**Output format — V5 marginally better; both broken on the same axis.** V5 adds the macro context block and the macro-deterioration exit trigger (keep both). V4 has an internal contradiction: tiers define 65–74 as "Deploy conservatively" but output says "only show trades scoring 70+", so a 68 is simultaneously deployable and invisible. V5's tiers align with its threshold. **Both define only what a candidate looks like — neither defines the zero-trade day**, which both philosophies insist is the modal outcome. The most common output of both frameworks is unspecified. V6 must make the zero-trade report a first-class format.

## 1.3 Error modes

**V5 checked against the known failure history:**
- *OTM strikes violating a delta floor:* **Partially repeats it — by design.** No delta floor exists, and the risk-on structure rule explicitly permits "Moderate OTM / Higher convexity." This is the documented failure mode reintroduced as a feature.
- *Ignored binary-event disqualifiers:* **Not repeated.** V5's binary-event gate is intact and identical to V4's (14 days, earnings/FDA/mergers/launches).
- *Names lacking genuine panic drawdowns:* **Vulnerable via vagueness.** With no drawdown bands (V4: "down 10–20% in 2–5 days"), V5's "prioritize panic" can be satisfied rhetorically. V4's numeric bands are the defense; V5 removed them.

**V5's own error modes:**
- Macro double-counting → threshold inflation in risk-on regimes (argued above).
- "INVALIDATES the screen" rule that is unfollowable with your real data access.
- "Gamma positioning if available" — no source exists in your stack; invites fabrication.
- Deployment tier "95–110 Aggressive deployment" — the top 10 points of the range are macro beta, so max-aggression is partly regime-conditional rather than trade-conditional.

**V4's own blind spots (independent of V5):**
- **Zero macro awareness** — the big one, argued above.
- **Positioning bands misfit the large-cap SaaS universe** (scores your whole hunting ground as "saturated").
- **Valuation bands calibrated for value/energy**, not quality growth.
- 65–74 tier vs. 70+ display contradiction.
- No per-contract IV check — the framework buys panic, panic means rich IV, and nothing measures whether the premium itself is the overpriced asset.
- Example anchors (DVN/PLTR/SOFI/NBIS) will silently rot as those stories age.
- Biotech Phase-3 carve-out is a gameable exception with no relevance to the mandate.

**Shared error modes (both files):**
- "Expected value >3:1 in base case" checklist item is undefined in both — 3:1 of what? (Upside:downside ratio? Probability-weighted multiple?) Vague enough to always pass. V6 must define it once, precisely.
- No universe definition — "SaaSpocalypse" exists only in your chat history, not in either spec.
- No data-source protocol, no positions/portfolio-correlation gate, no zero-trade output, no staleness/verification stamps.
- Both mission statements mandate finding "THE ONE/single highest-probability trade deployable tomorrow" — in direct tension with "most days produce ZERO trades." Both inherit the same self-contradiction; V6's mission must be rewritten as *render a verdict*, not *find a trade*.

## 1.4 Verdict

**V4 is the stronger framework overall, and it's not close on the dimensions that prevent bad trades.** Its banded, example-grounded rubrics are auditable and inflation-resistant; its delta/structure discipline encodes the deep-ITM survivability identity; and its "what this screener learned" section is real production scar tissue V5 simply doesn't have. V5 reads like a well-organized restatement of V4's philosophy with the operational precision stripped out — except in one area.

**That one area is genuinely important: V5 is right that a LEAPS framework with no macro regime layer is flying blind**, and V4 has none at all. But V5's *implementation* of macro (additive points + unfollowable mandatory data collection + reopened OTM permission) would make the framework looser exactly when markets feel best, which is when this framework's discipline matters most.

**Adopt from V5 into V6:** macro-mismatch hard disqualifier; single-macro-factor dependency disqualifier; macro-deterioration exit trigger; IV-environment→structure conditioning (bounded by a delta floor); the "macro-sensitive catalysts score lower" discount rule; its Sector Rotation Analysis section (elevated into V6's Rotation Radar — early institutional rotation detection); dropping the biotech carve-out; tier/threshold alignment (its 70+ display matches its tiers).

**Adopt from V4:** the entire scoring chassis (100-pt scale, banded rubrics), delta-banded structure scoring, duration rules, the discipline checklist, the lessons-learned mechanism (institutionalize it as a living section), and the top-1–3 output template.

**Neither version is deployable as-is for your stated mandate:** no universe definition, no data-source protocol, positioning/valuation bands miscalibrated for large-cap SaaS (V4) or absent (V5), no delta floor, no zero-trade output, no portfolio gate. V6 is a real synthesis, not a merge.

---

