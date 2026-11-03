"""§11's scoring aggregator.

§11's eight dimensions are mostly qualitative judgment calls — thesis fit,
mispricing, fundamental confirmation, valuation survivability, positioning,
catalyst path, invalidation clarity — which is exactly why ADR 0010 assigns
"scoring the qualitative dimensions of §11" to the model, not the engine.
What IS mechanical, and was missing from the Phase 2-3 build until Phase 5
needed it: summing the eight scores, checking each dimension's sub-gate
minimum, and comparing the total against the regime-adjusted threshold from
`engine.macro.RestrictedRegimeResult`. That's this module — deliberately
thin, because the eight numbers themselves are never invented here.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import get


@dataclass(frozen=True)
class ScoreSheet:
    """Each field is a score the model assigned from evidence, not a value
    this module computes. `option_implementation` is the one dimension with
    a real mechanical anchor — it should reflect whether `engine.gates`'
    liquidity vetoes and `engine.optmodel`'s IV-outlier check actually
    passed, not a separate impression."""

    thesis_fit: int
    mispricing: int
    fundamental_confirm: int
    valuation_survival: int
    option_implementation: int
    positioning: int
    catalyst_path: int
    invalidation_clarity: int


@dataclass(frozen=True)
class SubGateResult:
    dimension: str
    score: int
    minimum: int
    passed: bool


@dataclass(frozen=True)
class ScoringResult:
    total: int
    threshold: int
    sub_gates: list[SubGateResult]
    passes_sub_gates: bool
    passes_threshold: bool

    @property
    def clears(self) -> bool:
        return self.passes_sub_gates and self.passes_threshold


_FIELD_TO_CONFIG_KEY = {
    "thesis_fit": "thesis_fit",
    "mispricing": "mispricing",
    "fundamental_confirm": "fundamental_confirm",
    "valuation_survival": "valuation_survival",
    "option_implementation": "option_implementation",
    "positioning": "positioning",
    "catalyst_path": "catalyst_path",
    "invalidation_clarity": "invalidation_clarity",
}


def aggregate_score(cfg: dict, sheet: ScoreSheet, effective_threshold: int) -> ScoringResult:
    """§11: "Every sub-gate is mandatory. A candidate that totals 88 but
    scores 11 on Thesis Fit is REJECTED, not deployed." `effective_threshold`
    comes from `engine.macro.RestrictedRegimeResult.score_threshold` (75
    normal / 80 restricted) — not re-derived here, same pattern as
    `engine.sizing.compute_f_trade`'s `kelly_multiplier` parameter.
    """
    scoring_cfg = get(cfg, "scoring")
    sub_gates = []
    for field, cfg_key in _FIELD_TO_CONFIG_KEY.items():
        score = getattr(sheet, field)
        spec = scoring_cfg[cfg_key]
        minimum = spec["min"] if spec["min"] is not None else 0
        sub_gates.append(SubGateResult(dimension=field, score=score, minimum=minimum, passed=score >= minimum))

    total = sum(getattr(sheet, f) for f in _FIELD_TO_CONFIG_KEY)
    return ScoringResult(
        total=total,
        threshold=effective_threshold,
        sub_gates=sub_gates,
        passes_sub_gates=all(g.passed for g in sub_gates),
        passes_threshold=total >= effective_threshold,
    )



def option_implementation_score(cfg: dict, checks, spread_pct: float | None = None,
                                open_interest: int | None = None) -> int:
    """§11's option_implementation dimension (15 points, minimum 10), computed
    from the preliminary chain read's `engine.gates` checks rather than an
    impression (ADR 0021). The same thin chain was scored anywhere from 3 to 7
    on different days through 2026-11-03, and this was the most common S11
    sub-gate failure.

    `checks` is what `evaluate_liquidity_vetoes` returns (any subset that
    includes the four hard vetoes). All four passing (`dte_range`,
    `quoted_spread`, `open_interest`, `volume_20d_median`) meets the
    sub-gate minimum of 10, and each one failing costs 3 below that. Above
    10: +2 for a spread at most half the ceiling, +2 for open interest at
    least twice the floor, +1 for a passed `iv_local_outlier` check."""
    by_name = {c.name: c for c in checks}
    hard = ["dte_range", "quoted_spread", "open_interest", "volume_20d_median"]
    failed = sum(1 for n in hard if not (n in by_name and by_name[n].passed))
    if failed:
        return max(0, 10 - 3 * failed)
    score = 10
    if spread_pct is not None and spread_pct <= get(cfg, "option_vetoes.quoted_spread_max_pct") / 2:
        score += 2
    if open_interest is not None and open_interest >= 2 * get(cfg, "option_vetoes.open_interest_min"):
        score += 2
    if "iv_local_outlier" in by_name and by_name["iv_local_outlier"].passed:
        score += 1
    return score
