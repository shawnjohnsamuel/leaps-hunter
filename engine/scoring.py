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
