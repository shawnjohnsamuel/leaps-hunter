"""§7's pre-scoring event/quality gates and §12.1's liquidity/execution
vetoes. Any single failure rejects the candidate (§7) or the contract
(§12.1) — this module never aggregates toward a score, only toward a
pass/fail list.

Same split as engine.patterns (ADR 0010): mechanical checks are computed
here; judgment calls ("single customer/commodity/approval/macro
dependency," "credible near-term FCF path," "unresolved governance risk")
and data this engine has no wired source for (a binary-event date from
Robinhood's earnings calendar, 20-day median contract volume, a computed
fair value from the not-yet-built engine.optmodel) arrive as explicit
optional inputs. **Every check here returns a definite GateCheck even when
its inputs are missing — `passed=False` with a reason, never a silent
pass.** This matches ADR 0004's "unverifiable = undeployable" rule, applied
to every gate in this module rather than only to liquidity.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from .config import get


@dataclass(frozen=True)
class GateCheck:
    name: str
    passed: bool
    reason: str


def failing(checks: list[GateCheck]) -> list[GateCheck]:
    return [c for c in checks if not c.passed]


def all_passed(checks: list[GateCheck]) -> bool:
    return all(c.passed for c in checks)


# --------------------------------------------------- §7 pre-scoring gates ---

def binary_event_gate(days_to_next_binary_event: int | None, cfg: dict) -> GateCheck:
    """The earnings veto has no spread exception (§7): this check does not
    take a structure parameter, and nothing about the candidate's intended
    structure ever waives it."""
    blackout = get(cfg, "event_gates.binary_event_blackout_days")
    if days_to_next_binary_event is None:
        return GateCheck("binary_event", False, "next binary event date unknown")
    passed = days_to_next_binary_event > blackout
    return GateCheck(
        "binary_event", passed,
        f"{days_to_next_binary_event}d to next binary event (blackout {blackout}d)",
    )


def valuation_insanity_gate(
    is_unprofitable: bool | None,
    price_to_sales: float | None,
    credible_fcf_path: bool | None,
    cfg: dict,
) -> GateCheck:
    max_ps = get(cfg, "event_gates.max_ps_if_unprofitable")
    if is_unprofitable is None or (is_unprofitable and price_to_sales is None):
        return GateCheck("valuation_insanity", False, "profitability or P/S data incomplete")
    if not is_unprofitable:
        return GateCheck("valuation_insanity", True, "profitable")
    if price_to_sales <= max_ps:
        return GateCheck("valuation_insanity", True, f"P/S {price_to_sales} <= {max_ps}")
    if credible_fcf_path:
        return GateCheck(
            "valuation_insanity", True,
            f"P/S {price_to_sales} > {max_ps} but a credible near-term FCF path exists",
        )
    return GateCheck(
        "valuation_insanity", False,
        f"unprofitable, P/S {price_to_sales} > {max_ps}, no credible FCF path",
    )


def single_variable_dependency_gate(depends_on_single_variable: bool | None) -> GateCheck:
    if depends_on_single_variable is None:
        return GateCheck("single_variable_dependency", False, "not yet assessed")
    reason = (
        "thesis depends on a single customer/commodity/approval/macro factor"
        if depends_on_single_variable
        else "multiple independent drivers"
    )
    return GateCheck("single_variable_dependency", not depends_on_single_variable, reason)


def catalyst_duration_gate(catalyst_horizon_days: int | None, option_dte_days: int | None) -> GateCheck:
    if catalyst_horizon_days is None or option_dte_days is None:
        return GateCheck("catalyst_duration", False, "catalyst horizon or option DTE unknown")
    passed = option_dte_days >= catalyst_horizon_days
    return GateCheck(
        "catalyst_duration", passed,
        f"catalyst horizon {catalyst_horizon_days}d vs option DTE {option_dte_days}d",
    )


def governance_risk_gate(unresolved_risk: bool | None) -> GateCheck:
    if unresolved_risk is None:
        return GateCheck("governance_risk", False, "not yet assessed")
    reason = (
        "unresolved accounting/solvency/governance risk"
        if unresolved_risk
        else "no unresolved risk flagged"
    )
    return GateCheck("governance_risk", not unresolved_risk, reason)


@dataclass(frozen=True)
class PreScoringGateInputs:
    days_to_next_binary_event: int | None = None
    is_unprofitable: bool | None = None
    price_to_sales: float | None = None
    credible_fcf_path: bool | None = None
    depends_on_single_variable: bool | None = None
    catalyst_horizon_days: int | None = None
    option_dte_days: int | None = None
    unresolved_accounting_or_governance_risk: bool | None = None


def evaluate_pre_scoring_gates(cfg: dict, inputs: PreScoringGateInputs) -> list[GateCheck]:
    return [
        binary_event_gate(inputs.days_to_next_binary_event, cfg),
        valuation_insanity_gate(
            inputs.is_unprofitable, inputs.price_to_sales, inputs.credible_fcf_path, cfg
        ),
        single_variable_dependency_gate(inputs.depends_on_single_variable),
        catalyst_duration_gate(inputs.catalyst_horizon_days, inputs.option_dte_days),
        governance_risk_gate(inputs.unresolved_accounting_or_governance_risk),
    ]


# ------------------------------------------------ §12.1 liquidity vetoes ----

def dte_gate(dte_days: int, cfg: dict) -> GateCheck:
    lo, hi = get(cfg, "option_vetoes.dte_range")
    return GateCheck("dte_range", lo <= dte_days <= hi, f"{dte_days}d (need {lo}-{hi}d)")


def quote_age_gate(quote_age_seconds: float, cfg: dict) -> GateCheck:
    max_age = get(cfg, "option_vetoes.quote_age_max_seconds")
    return GateCheck(
        "quote_age", quote_age_seconds <= max_age, f"{quote_age_seconds}s (max {max_age}s)"
    )


def spread_gate(bid: float, ask: float, cfg: dict) -> GateCheck:
    if bid <= 0 or ask <= 0 or ask < bid:
        return GateCheck("quoted_spread", False, f"invalid quote bid={bid} ask={ask}")
    spread_pct = (ask - bid) / ((ask + bid) / 2) * 100
    max_pct = get(cfg, "option_vetoes.quoted_spread_max_pct")
    return GateCheck(
        "quoted_spread", spread_pct <= max_pct, f"{spread_pct:.2f}% (max {max_pct}%)"
    )


def open_interest_gate(open_interest: int, cfg: dict) -> GateCheck:
    min_oi = get(cfg, "option_vetoes.open_interest_min")
    return GateCheck("open_interest", open_interest >= min_oi, f"{open_interest} (min {min_oi})")


def volume_gate(median_20d_volume: float | None, cfg: dict) -> GateCheck:
    min_vol = get(cfg, "option_vetoes.median_daily_volume_20d_min")
    if median_20d_volume is None:
        return GateCheck("volume_20d_median", False, "20-day median contract volume unavailable")
    return GateCheck(
        "volume_20d_median", median_20d_volume >= min_vol, f"{median_20d_volume} (min {min_vol})"
    )


def marketable_limit_gate(
    modeled_entry_cost: float | None, high_fill_rate_buy_price: float | None
) -> GateCheck:
    """[ASSUMPTION]: §12.1 specifies a live 30-minute marketable-limit fill
    test, which has no read-only implementation — placing an order is
    prohibited (the annex A tool contract). Robinhood's
    `high_fill_rate_buy_price`, a conservative estimate of where a
    marketable order would actually fill, stands in for it
    (docs/phase-0-findings.md); revisit against real fills once §17.7's
    post-trade review has data.
    """
    if modeled_entry_cost is None:
        return GateCheck(
            "marketable_limit_fill", False,
            "modeled entry cost not yet computed (requires engine.optmodel, Phase 3)",
        )
    if high_fill_rate_buy_price is None:
        return GateCheck("marketable_limit_fill", False, "fill-rate estimate unavailable")
    passed = high_fill_rate_buy_price <= modeled_entry_cost
    return GateCheck(
        "marketable_limit_fill", passed,
        f"est. fill {high_fill_rate_buy_price} vs modeled entry {modeled_entry_cost}",
    )


def iv_local_outlier_gate(
    strike_iv: float | None, neighbor_ivs: list[float], z_threshold: float = 2.0
) -> GateCheck:
    """[ASSUMPTION]: §12.1 requires the strike's ask IV not be "a local
    outlier relative to neighboring-strike midpoint IV," without naming a
    statistic. A z-score against the neighboring strikes' IV at a 2-sigma
    default threshold is used here; §20 does not specify an exact value to
    override it with."""
    if strike_iv is None:
        return GateCheck("iv_local_outlier", False, "strike IV unavailable")
    if len(neighbor_ivs) < 2:
        return GateCheck("iv_local_outlier", False, "fewer than 2 neighboring strikes to compare")
    mean = statistics.fmean(neighbor_ivs)
    sd = statistics.stdev(neighbor_ivs)
    if sd == 0:
        z = 0.0 if strike_iv == mean else float("inf")
    else:
        z = (strike_iv - mean) / sd
    passed = abs(z) <= z_threshold
    return GateCheck(
        "iv_local_outlier", passed,
        f"IV {strike_iv} vs neighbor mean {mean:.4f} (z={z:.2f}, threshold {z_threshold})",
    )


def premium_vs_fair_value_gate(entry_premium: float, fair_value: float | None, cfg: dict) -> GateCheck:
    max_over = get(cfg, "option_vetoes.max_premium_over_fair_value_pct")
    if fair_value is None:
        return GateCheck(
            "premium_vs_fair_value", False,
            "fair value not yet computed (requires engine.optmodel, Phase 3)",
        )
    over_pct = (entry_premium / fair_value - 1) * 100
    return GateCheck(
        "premium_vs_fair_value", over_pct <= max_over, f"{over_pct:.1f}% over fair value (max {max_over}%)"
    )


@dataclass(frozen=True)
class LiquidityVetoInputs:
    dte_days: int
    quote_age_seconds: float
    bid: float
    ask: float
    open_interest: int
    entry_premium: float
    median_20d_volume: float | None = None
    modeled_entry_cost: float | None = None
    high_fill_rate_buy_price: float | None = None
    strike_iv: float | None = None
    neighbor_ivs: list[float] = field(default_factory=list)
    fair_value: float | None = None


def evaluate_liquidity_vetoes(cfg: dict, inputs: LiquidityVetoInputs) -> list[GateCheck]:
    return [
        dte_gate(inputs.dte_days, cfg),
        quote_age_gate(inputs.quote_age_seconds, cfg),
        spread_gate(inputs.bid, inputs.ask, cfg),
        open_interest_gate(inputs.open_interest, cfg),
        volume_gate(inputs.median_20d_volume, cfg),
        marketable_limit_gate(inputs.modeled_entry_cost, inputs.high_fill_rate_buy_price),
        iv_local_outlier_gate(inputs.strike_iv, inputs.neighbor_ivs),
        premium_vs_fair_value_gate(inputs.entry_premium, inputs.fair_value, cfg),
    ]
