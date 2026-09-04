"""§10's four permitted entry patterns.

Each pattern mixes two kinds of conditions, and this module treats them
differently on purpose (ADR 0010):

- **Mechanical** conditions — a drawdown %, a 20/120-day high, an NTM
  estimate revision — are computed here from price series and
  `engine.sources.NTMResult`.
- **Judgment** conditions — "2 of 5 fundamentals accelerating," "pricing or
  incremental-margin evidence," a multiple-expansion ratio, backlog-vs-
  revenue growth — require reading company disclosures or data this engine
  has no wired source for. Those arrive as explicit, typed, optional
  parameters that the calling skill fills in from its own research. This
  module never invents a number for one of these; a pattern whose judgment
  input is missing is **not confirmed**, never silently passed — §3: an
  unobtainable required metric disqualifies, it does not default to true.

All patterns return a `PatternResult` with `qualifies` (the quantitative
minimum) and `confirmed` (the confirmation column) evaluated separately,
since §10 requires both for a name to clear a pattern.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from .config import get
from .priceseries import daily_returns, pct_change, rolling_max
from .sources import NTMResult


@dataclass(frozen=True)
class PatternResult:
    pattern: str
    qualifies: bool
    confirmed: bool
    reasons: list[str] = field(default_factory=list)

    @property
    def clears(self) -> bool:
        return self.qualifies and self.confirmed


def _ntm_reasons(ntm: NTMResult | None, min_pct: float, label: str) -> tuple[bool, list[str]]:
    if ntm is None:
        return False, [f"{label}: no NTM estimate data provided"]
    if not ntm.available:
        return False, [f"{label}: unavailable — {ntm.reason}"]
    ok = ntm.revision_pct >= min_pct
    return ok, [f"{label}: {ntm.revision_pct:+.2f}% over 60d (need >= {min_pct:+.0f}%)"]


# ------------------------------------------------------------------ panic ---

def panic_pattern(cfg: dict, prices: list[float], ntm: NTMResult | None) -> PatternResult:
    """`prices` ascending by date (oldest first); needs at least
    `window_sessions[1] + 1` entries to evaluate the drawdown windows, and
    ideally a longer history for a meaningful daily-return stdev.
    """
    g = get(cfg, "entry_patterns.panic")
    lo_pct, hi_pct = g["drawdown_pct_range"]
    lo_w, hi_w = g["window_sessions"]
    sigma_k = g["sigma_alternative"]
    max_cut = g["max_ntm_consensus_cut_pct"]

    reasons = []
    qualifies_by_drawdown = False
    deepest = 0.0
    for w in range(lo_w, hi_w + 1):
        if len(prices) <= w:
            continue
        dd = pct_change(prices, w)  # negative for a decline
        deepest = min(deepest, dd)
        if -hi_pct <= dd <= -lo_pct:
            qualifies_by_drawdown = True
    reasons.append(f"deepest {lo_w}-{hi_w}d drawdown {deepest:.1f}% (need {-hi_pct} to {-lo_pct}%)")

    returns = daily_returns(prices)
    sigma = _stdev(returns)
    qualifies_by_sigma = bool(sigma) and bool(returns) and returns[-1] <= -sigma_k * sigma
    if sigma:
        reasons.append(f"latest daily return {returns[-1]*100:+.1f}% vs {sigma_k}sigma "
                        f"= {-sigma_k*sigma*100:.1f}%")

    qualifies = qualifies_by_drawdown or qualifies_by_sigma

    # NTM consensus-cut confirmation runs on EPS, not revenue: Alpha Vantage's
    # revenue estimate has no _60_days_ago field (see docs/data-sources.md).
    if ntm is None:
        confirmed, ntm_reasons = False, ["NTM consensus-cut check: no NTM estimate data provided"]
    elif not ntm.available:
        confirmed, ntm_reasons = False, [f"NTM consensus-cut check: unavailable — {ntm.reason}"]
    else:
        cut = max(0.0, -ntm.revision_pct)  # magnitude of a CUT only; an improvement is not a cut
        confirmed = cut <= max_cut
        ntm_reasons = [f"NTM EPS revision {ntm.revision_pct:+.2f}% "
                       f"(consensus cut {cut:.1f}%, max allowed {max_cut}%)"]

    return PatternResult("panic", qualifies, confirmed, reasons + ntm_reasons)


def _stdev(values: list[float]) -> float:
    return statistics.stdev(values) if len(values) >= 2 else 0.0


# ---------------------------------------------------------- quiet inflection

@dataclass(frozen=True)
class QuietInflectionInputs:
    """`accelerating_metrics_count` and `is_range_bound` are judgment calls
    from the calling skill's reading of company disclosures — this module
    never derives them. `relative_underperformance_pts` is the stock's
    return minus its sector's return over the same lookback, in points;
    compute it from price series before calling if available."""

    accelerating_metrics_count: int
    ntm: NTMResult | None
    relative_underperformance_pts: float | None = None
    is_range_bound: bool | None = None


def quiet_inflection_pattern(cfg: dict, inputs: QuietInflectionInputs) -> PatternResult:
    g = get(cfg, "entry_patterns.quiet_inflection")
    reasons = []

    qualifies = inputs.accelerating_metrics_count >= g["accelerating_metrics_min"]
    reasons.append(
        f"{inputs.accelerating_metrics_count} of 5 fundamentals accelerating "
        f"(need >= {g['accelerating_metrics_min']})"
    )

    revision_ok, revision_reasons = _ntm_reasons(
        inputs.ntm, g["estimate_revision_min_pct_60d"], "NTM revenue/EPS revision"
    )
    reasons += revision_reasons

    underperf_ok = (
        inputs.relative_underperformance_pts is not None
        and inputs.relative_underperformance_pts >= g["relative_underperformance_min_pts"]
    )
    range_ok = bool(inputs.is_range_bound)
    reasons.append(
        f"underperformance={inputs.relative_underperformance_pts} "
        f"(need >= {g['relative_underperformance_min_pts']}pts) OR range_bound={inputs.is_range_bound}"
    )

    confirmed = revision_ok and (underperf_ok or range_ok)
    return PatternResult("quiet_inflection", qualifies, confirmed, reasons)


# ----------------------------------------------------------------- breakout -

@dataclass(frozen=True)
class BreakoutInputs:
    """`multiple_expansion_ratio` (actual multiple expansion ÷ fundamental-
    estimate improvement) is not derivable from a price series alone — it
    needs a valuation-multiple time series this engine has no wired source
    for. Supply it from the calling skill's own analysis; None leaves the
    confirmation unresolved (not confirmed), never assumed to pass."""

    ntm: NTMResult | None
    multiple_expansion_ratio: float | None = None


def breakout_pattern(cfg: dict, prices: list[float], inputs: BreakoutInputs) -> PatternResult:
    g = get(cfg, "entry_patterns.breakout")
    lo_days, hi_days = g["high_lookback_days"]
    max_gain = g["max_30d_gain_pct"]

    reasons = []
    new_high = False
    for window in (lo_days, hi_days):
        if len(prices) >= window and prices[-1] >= rolling_max(prices, window):
            new_high = True
    reasons.append(f"new {lo_days}- or {hi_days}-day high: {new_high}")

    gain_30d = pct_change(prices, 30) if len(prices) > 30 else None
    gain_ok = gain_30d is not None and gain_30d <= max_gain
    reasons.append(f"30d gain {gain_30d if gain_30d is None else round(gain_30d, 1)}% "
                    f"(must be <= {max_gain}%)")

    qualifies = new_high and gain_ok

    revision_ok, revision_reasons = _ntm_reasons(
        inputs.ntm, g["estimate_revision_min_pct_60d"], "NTM FCF/EPS revision"
    )
    reasons += revision_reasons

    expansion_ok = (
        inputs.multiple_expansion_ratio is not None
        and inputs.multiple_expansion_ratio < g["max_multiple_expansion_ratio"]
    )
    reasons.append(
        f"multiple expansion ratio={inputs.multiple_expansion_ratio} "
        f"(must be < {g['max_multiple_expansion_ratio']})"
    )

    confirmed = revision_ok and expansion_ok
    return PatternResult("breakout", qualifies, confirmed, reasons)


# --------------------------------------------------- bottleneck expansion ---

@dataclass(frozen=True)
class BottleneckExpansionInputs:
    """Backlog/order data is fundamentals-derived (SEC filings, investor
    presentations) — no wired source computes it generically here. The
    option-valuation check depends on engine.optmodel, not built until
    Phase 3; a None there leaves confirmation unresolved, not passed."""

    backlog_vs_revenue_growth_pts: float | None = None
    backlog_to_revenue_stable_or_rising: bool | None = None
    pricing_or_margin_evidence: bool | None = None
    option_valuation_passed: bool | None = None


def bottleneck_expansion_pattern(
    cfg: dict, prices: list[float], inputs: BottleneckExpansionInputs
) -> PatternResult:
    g = get(cfg, "entry_patterns.bottleneck_expansion")
    reasons = []

    qualifies = (
        inputs.backlog_vs_revenue_growth_pts is not None
        and inputs.backlog_vs_revenue_growth_pts >= g["backlog_vs_revenue_growth_min_pp"]
        and bool(inputs.backlog_to_revenue_stable_or_rising)
    )
    reasons.append(
        f"backlog-vs-revenue growth={inputs.backlog_vs_revenue_growth_pts}pts "
        f"(need >= {g['backlog_vs_revenue_growth_min_pp']}pp), "
        f"stable_or_rising={inputs.backlog_to_revenue_stable_or_rising}"
    )

    gain_30d = pct_change(prices, 30) if len(prices) > 30 else None
    gain_ok = gain_30d is not None and gain_30d <= g["max_30d_gain_pct"]
    reasons.append(
        f"30d gain {gain_30d if gain_30d is None else round(gain_30d, 1)}% "
        f"(must be <= {g['max_30d_gain_pct']}%)"
    )

    pricing_ok = bool(inputs.pricing_or_margin_evidence)
    option_ok = bool(inputs.option_valuation_passed)
    reasons.append(
        f"pricing/margin evidence={inputs.pricing_or_margin_evidence}, "
        f"option-valuation passed={inputs.option_valuation_passed} (Phase 3 dependency)"
    )

    confirmed = gain_ok and pricing_ok and option_ok
    return PatternResult("bottleneck_expansion", qualifies, confirmed, reasons)
