"""§12's executable, friction-adjusted option pricing model, plus §13.1's
delta policy and §13.2's vertical-spread rule (structure eligibility lives
here because it is evaluated on the same priced structures this module
produces; §13.3 feasibility and §14 sizing live in engine.sizing).

Calls only: v7's structures are long calls and bull call debit spreads, so
no put pricing is implemented. Black-Scholes via `math.erf` — no scipy/numpy
(ADR 0010).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .config import get
from .gates import GateCheck


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_call_price(S: float, K: float, T: float, r: float, q: float, sigma: float) -> float:
    """Black-Scholes European call price. Degenerates to intrinsic value at
    T<=0 or sigma<=0 rather than raising, since scenario models legitimately
    walk T down to (and past) expiry."""
    if T <= 0 or sigma <= 0:
        return max(0.0, S - K)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * math.exp(-q * T) * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)


def bs_call_delta(S: float, K: float, T: float, r: float, q: float, sigma: float) -> float:
    if T <= 0 or sigma <= 0:
        return 1.0 if S > K else 0.0
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    return math.exp(-q * T) * _norm_cdf(d1)


# ------------------------------------------------- §12.2 executable pricing -

def executable_entry(ask: float, bid: float, fees: float, cfg: dict) -> float:
    """P0_entry = A0 + entry_slippage_fraction_of_spread*(A0-B0) + F0.
    Never the midpoint — §12.2 is explicit that a midpoint EV is not a
    tradable result and must not be reported as one."""
    slip = get(cfg, "pricing.entry_slippage_fraction_of_spread")
    return ask + slip * (ask - bid) + fees


def stressed_spread_pct(
    w0_pct: float, sigma_atm_now: float, sigma_atm_scenario: float,
    spot_scenario: float, spot_now: float, cfg: dict,
) -> float:
    """wj: the scenario-stressed quoted spread %, widening under an IV
    spike and/or a sharp drawdown."""
    iv_coef = get(cfg, "pricing.exit_stress_iv_coefficient")
    dd_coef = get(cfg, "pricing.exit_stress_drawdown_coefficient")
    dd_threshold = get(cfg, "pricing.exit_stress_drawdown_threshold")
    iv_term = iv_coef * max(0.0, (sigma_atm_scenario - sigma_atm_now) / sigma_atm_now)
    dd_term = dd_coef * (1.0 if spot_scenario < dd_threshold * spot_now else 0.0)
    return w0_pct * (1 + iv_term + dd_term)


def executable_exit(
    spot_scenario: float, strike: float, tau_remaining: float, r: float, q: float,
    sigma_exit: float, w0_pct: float, sigma_atm_now: float, sigma_atm_scenario: float,
    spot_now: float, dollar_spread_width: float, fees: float, cfg: dict,
) -> float:
    """Pj_exit = max(0, C(...)*(1 - wj/2) - width_penalty*Wj - Fj), using a
    scenario-specific IV (`sigma_exit`) — never a flat IV assumption
    (§12.2)."""
    price = bs_call_price(spot_scenario, strike, tau_remaining, r, q, sigma_exit)
    wj_pct = stressed_spread_pct(w0_pct, sigma_atm_now, sigma_atm_scenario, spot_scenario, spot_now, cfg)
    haircut = get(cfg, "pricing.exit_spread_haircut_fraction")
    width_penalty = get(cfg, "pricing.exit_width_penalty_fraction")
    exit_price = price * (1 - haircut * (wj_pct / 100.0)) - width_penalty * dollar_spread_width - fees
    return max(0.0, exit_price)


# ------------------------------------------------------ §12.3 scenario EV --

@dataclass(frozen=True)
class Scenario:
    label: str
    probability: float
    exit_price: float


@dataclass(frozen=True)
class ScenarioModelResult:
    entry_price: float
    returns: dict[str, float]
    ev_net: float
    expected_loss: float
    ev_to_el: float | None
    passes_ev_net: bool
    passes_ev_to_el: bool

    @property
    def passes_acceptance(self) -> bool:
        return self.passes_ev_net and self.passes_ev_to_el


def evaluate_scenarios(cfg: dict, entry_price: float, scenarios: list[Scenario]) -> ScenarioModelResult:
    """Rj=(Pj_exit-P0)/P0; EV_net=sum(pj*Rj); EL=sum(pj*max(0,-Rj)).
    Checks §12.3's first two acceptance criteria (EV_net>0, EV_net/EL>=min);
    the third (robust expected log growth>0) is checked in engine.sizing
    once Kelly runs on these same returns."""
    returns = {s.label: (s.exit_price - entry_price) / entry_price for s in scenarios}
    ev_net = sum(s.probability * returns[s.label] for s in scenarios)
    el = sum(s.probability * max(0.0, -returns[s.label]) for s in scenarios)
    ev_to_el = ev_net / el if el > 0 else None
    return ScenarioModelResult(
        entry_price=entry_price,
        returns=returns,
        ev_net=ev_net,
        expected_loss=el,
        ev_to_el=ev_to_el,
        passes_ev_net=ev_net > get(cfg, "acceptance.ev_net_min"),
        passes_ev_to_el=(ev_to_el is not None and ev_to_el >= get(cfg, "acceptance.ev_to_expected_loss_min")),
    )


# ------------------------------------------------------- §13.1 delta policy -

@dataclass(frozen=True)
class DeltaPolicyResult:
    permitted: bool
    band: str
    reason: str


def evaluate_delta_policy(
    cfg: dict, delta: float, hard_gate_active: bool, restricted: bool,
    variance_and_es_tests_passed: bool | None = None,
) -> DeltaPolicyResult:
    """§13.1. The 0.55-0.70 convexity exception is granted only on a
    CONFIRMED pass of §15's variance/ES tests — None (not yet evaluated)
    never grants it, same fail-closed discipline as the rest of the engine.
    """
    if hard_gate_active:
        return DeltaPolicyResult(False, "hard_gate_active", "no new long LEAPS while a §6.1 hard gate is active")

    normal_lo, normal_hi = get(cfg, "delta_policy.normal")
    restricted_lo, restricted_hi = get(cfg, "delta_policy.restricted")
    convex_lo, _convex_hi = get(cfg, "delta_policy.convexity_exception")

    if restricted:
        ok = restricted_lo <= delta <= restricted_hi
        return DeltaPolicyResult(
            ok, "restricted",
            f"{delta} {'within' if ok else 'outside'} restricted-regime band [{restricted_lo},{restricted_hi}]",
        )

    if normal_lo <= delta <= normal_hi:
        return DeltaPolicyResult(True, "normal", f"{delta} within normal band [{normal_lo},{normal_hi}]")

    if convex_lo <= delta < normal_lo:
        if variance_and_es_tests_passed:
            return DeltaPolicyResult(True, "convexity_exception", f"{delta} in [{convex_lo},{normal_lo}) and §15 tests passed")
        return DeltaPolicyResult(False, "convexity_exception", f"{delta} in [{convex_lo},{normal_lo}) but §15 variance/ES tests not confirmed passing")

    return DeltaPolicyResult(False, "prohibited", f"{delta} outside all permitted delta bands for the current regime")


# ------------------------------------------------------- §13.2 spread rule --

def evaluate_spread_rule(
    cfg: dict,
    spread_robust_log_growth: float | None,
    outright_robust_log_growth: float | None,
    debit_fits_nav_budget: bool | None,
    both_legs_pass_liquidity: bool | None,
    prob_above_short_strike: float | None,
    spread_ev_positive_after_cap: bool | None,
) -> list[GateCheck]:
    """A spread is permitted, never mandated (§13.2) — this returns the
    five conditions ALL of which must hold for a spread to be selected over
    the outright; it never runs unprompted just because IV is elevated or a
    contract looks expensive (§19 bans exactly that)."""
    max_prob = get(cfg, "spread_rule.max_prob_above_short_strike")
    checks = []

    if spread_robust_log_growth is None or outright_robust_log_growth is None:
        checks.append(GateCheck("spread_beats_outright", False, "robust log growth not yet computed for one or both structures"))
    else:
        checks.append(GateCheck(
            "spread_beats_outright", spread_robust_log_growth > outright_robust_log_growth,
            f"spread {spread_robust_log_growth:.4f} vs outright {outright_robust_log_growth:.4f}",
        ))

    checks.append(GateCheck("fits_nav_budget", bool(debit_fits_nav_budget), f"debit_fits_nav_budget={debit_fits_nav_budget}"))
    checks.append(GateCheck("both_legs_liquid", bool(both_legs_pass_liquidity), f"both_legs_pass_liquidity={both_legs_pass_liquidity}"))

    if prob_above_short_strike is None:
        checks.append(GateCheck("short_strike_not_capping", False, "probability above short strike not estimated"))
    else:
        checks.append(GateCheck(
            "short_strike_not_capping", prob_above_short_strike <= max_prob,
            f"Pr(S_T>K_short)={prob_above_short_strike:.2%} (max {max_prob:.0%})",
        ))

    checks.append(GateCheck("positive_ev_after_cap", bool(spread_ev_positive_after_cap), f"spread_ev_positive_after_cap={spread_ev_positive_after_cap}"))
    return checks
