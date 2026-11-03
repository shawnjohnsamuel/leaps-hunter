"""§13.3's account feasibility and §14's robust fractional-Kelly sizing.

This module is where ADR 0013's `min_feasible_nav` finding actually gets
implemented: Phase 0 found that at realistic NAV, `N_max = 0` on every
permitted structure under §17's unvalidated-setup cap, and the plan's
response was to emit the NAV each rejection would have required rather than
a bare reject. `compute_feasibility` below is that computation.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .config import get


# ------------------------------------------------------- Kelly optimization -

def _kelly_growth(f: float, probs: list[float], rets: list[float]) -> float:
    total = 0.0
    for p, r in zip(probs, rets):
        x = 1 + f * r
        if x <= 0:
            return float("-inf")
        total += p * math.log(x)
    return total


def _kelly_derivative(f: float, probs: list[float], rets: list[float]) -> float:
    total = 0.0
    for p, r in zip(probs, rets):
        x = 1 + f * r
        if x <= 0:
            return float("-inf")
        total += p * r / x
    return total


def kelly_f_star(probs: list[float], rets: list[float], f_cap: float, tol: float = 1e-9) -> float:
    """argmax over f in [0, f_cap] of sum(p*log(1+f*r)) (§14). The objective
    is concave (a sum of log-of-affine terms), so its derivative is
    monotonically decreasing on the feasible domain and bisection on the
    derivative is exact and robust — no need for scipy (ADR 0010).

    `f_cap` is clipped below the point where any negative return would
    drive 1+f*r to zero, so the domain never includes an undefined point.
    """
    neg_rets = [r for r in rets if r < 0]
    if neg_rets:
        f_cap = min(f_cap, 0.999 / (-min(neg_rets)))
    if f_cap <= 0:
        return 0.0

    if _kelly_derivative(0.0, probs, rets) <= 0:
        return 0.0
    if _kelly_derivative(f_cap, probs, rets) >= 0:
        return f_cap

    lo, hi = 0.0, f_cap
    for _ in range(200):
        mid = (lo + hi) / 2
        if _kelly_derivative(mid, probs, rets) > 0:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return (lo + hi) / 2


def generate_posterior_draws(
    probs: list[float], rets: list[float], n_draws: int,
    prob_concentration: float = 50.0, return_noise_std: float = 0.05,
    seed: int | None = None,
) -> list[tuple[list[float], list[float]]]:
    """[ASSUMPTION]: §14 requires posterior draws of probabilities, returns,
    IV shocks and execution costs but does not specify a perturbation
    model — how much confidence to place in a base scenario estimate is
    inherently an analyst judgment (§17: all probabilities and returns are
    `[ASSUMPTION]`, calibrated out of sample over time).

    This default perturbs `probs` via a Dirichlet distribution centered on
    the given probabilities (`prob_concentration` — higher means tighter,
    more confident draws) and each of `rets` via independent Gaussian noise
    scaled to that return's own magnitude, collapsing IV-shock and
    execution-cost uncertainty into one noise term. Override this with a
    draw set built from the candidate's own comparable-cohort dispersion
    once §17's calibration record has one; nothing else in this module
    depends on draws coming from this specific generator.
    """
    rng = random.Random(seed)
    draws = []
    for _ in range(n_draws):
        gammas = [rng.gammavariate(max(p * prob_concentration, 1e-6), 1.0) for p in probs]
        total = sum(gammas)
        draw_probs = [g / total for g in gammas]
        draw_rets = [r + rng.gauss(0.0, return_noise_std * max(abs(r), 0.01)) for r in rets]
        draws.append((draw_probs, draw_rets))
    return draws


def robust_kelly_fraction(
    draws: list[tuple[list[float], list[float]]], f_cap: float, quantile: float = 0.10
) -> float:
    """f_robust = the `quantile`-th percentile of f* across `draws` (§14
    specifies the 10th percentile and at least 10,000 draws). Nearest-rank
    method — no interpolation is specified, and none is needed at this
    sample size."""
    f_stars = sorted(kelly_f_star(probs, rets, f_cap) for probs, rets in draws)
    idx = max(0, min(len(f_stars) - 1, int(quantile * len(f_stars))))
    return f_stars[idx]


# --------------------------------------------------------------- NAV caps ---

@dataclass(frozen=True)
class NAVCapInputs:
    """Existing-exposure fields default to 0.0 (no prior exposure) when
    unknown — never inferred, matching ADR 0013's account-selection lesson
    applied to concentration caps: the skill layer supplies these from
    Robinhood's actual position data (or the calibration ledger), and a
    missing value is a stated zero, not a silent guess."""

    is_calibrated: bool = False
    structure_type: str = "single_itm_or_spread"  # or "single_atm_convexity"
    existing_issuer_exposure_pct: float = 0.0
    existing_mechanism_exposure_pct: float = 0.0
    existing_leaps_book_exposure_pct: float = 0.0


def nav_caps(cfg: dict, inputs: NAVCapInputs) -> dict[str, float]:
    """Each §14 maximum-loss cap, converted from % of NAV to a fraction
    directly comparable to a Kelly `f`. §17: every position is capped at
    `caps_pct_of_nav.unvalidated_setup` until `is_calibrated` is True —
    there is no partial credit for "probably enough" observations."""
    caps = get(cfg, "sizing.caps_pct_of_nav")
    f_instrument = (caps[inputs.structure_type] if inputs.is_calibrated else caps["unvalidated_setup"]) / 100.0
    return {
        "f_instrument": f_instrument,
        "f_issuer": max(0.0, caps["single_issuer"] / 100.0 - inputs.existing_issuer_exposure_pct),
        "f_mechanism": max(0.0, caps["single_mechanism"] / 100.0 - inputs.existing_mechanism_exposure_pct),
        "f_portfolio": max(0.0, caps["total_leaps_book"] / 100.0 - inputs.existing_leaps_book_exposure_pct),
    }


@dataclass(frozen=True)
class SizingResult:
    f_robust: float
    f_trade: float
    binding_cap: str
    caps: dict[str, float]
    allocation_zero: bool


def compute_f_trade(f_robust: float, kelly_multiplier: float, caps: dict[str, float]) -> SizingResult:
    """f_trade = min(kelly_multiplier*f_robust, f_instrument, f_issuer,
    f_mechanism, f_portfolio). `kelly_multiplier` is 0.25 normal / 0.125
    restricted — read from `engine.macro.RestrictedRegimeResult.kelly_multiplier`,
    not re-derived here. "If f_robust <= 0, the allocation is zero. No
    exceptions" (§14) — checked before anything else runs."""
    if f_robust <= 0:
        return SizingResult(f_robust=f_robust, f_trade=0.0, binding_cap="f_robust<=0", caps=caps, allocation_zero=True)
    candidates = {"kelly": kelly_multiplier * f_robust, **caps}
    binding_cap, f_trade = min(candidates.items(), key=lambda kv: kv[1])
    return SizingResult(f_robust=f_robust, f_trade=f_trade, binding_cap=binding_cap, caps=caps, allocation_zero=f_trade <= 0)


# --------------------------------------------------- §13.3 account feasibility

@dataclass(frozen=True)
class FeasibilityResult:
    n_max: int
    feasible: bool
    min_feasible_nav: float
    # ADR 0021 diagnostics, so a rejection says how far off it is, not only that it failed:
    contract_pct_of_nav: float | None = None        # one contract's premium as % of NAV
    min_feasible_nav_calibrated: float | None = None  # same structure once §17 calibration lifts the cap


def compute_feasibility(f_trade: float, nav: float, entry_price_per_share: float,
                        calibrated_cap_pct: float | None = None) -> FeasibilityResult:
    """N_max = floor(f_trade*NAV / (100*P0_entry)) (§13.3). `entry_price_per_share`
    is the per-share premium (e.g. 79.79 for CRM's Jan-2028 $230 call, from
    engine.optmodel.executable_entry) — the ×100 contracts multiplier is
    applied here, matching §13.3's own formula, not baked into the caller's
    price.

    `min_feasible_nav` (ADR 0013) is the NAV at which N_max would just reach
    1: 100*P0_entry/f_trade. Every rejection can report exactly what it
    would take rather than a bare reject, and the figure rescales itself
    automatically as f_trade changes with calibration or regime.

    `calibrated_cap_pct` (the structure's `caps_pct_of_nav` entry, e.g. 1.25)
    adds `min_feasible_nav_calibrated`: the NAV one contract needs once the
    unvalidated-setup cap no longer applies. `contract_pct_of_nav` is the
    single-position loss one contract represents at today's NAV — the cap
    that would have been needed (ADR 0021)."""
    pct = (100 * entry_price_per_share / nav * 100.0) if nav > 0 and entry_price_per_share > 0 else None
    cal = (100 * entry_price_per_share / (calibrated_cap_pct / 100.0)
           if calibrated_cap_pct and entry_price_per_share > 0 else None)
    if f_trade <= 0 or entry_price_per_share <= 0:
        return FeasibilityResult(n_max=0, feasible=False, min_feasible_nav=float("inf"),
                                 contract_pct_of_nav=pct, min_feasible_nav_calibrated=cal)
    n_max = math.floor(f_trade * nav / (100 * entry_price_per_share))
    min_nav = (100 * entry_price_per_share) / f_trade
    return FeasibilityResult(n_max=n_max, feasible=n_max >= 1, min_feasible_nav=min_nav,
                             contract_pct_of_nav=pct, min_feasible_nav_calibrated=cal)


# ------------------------------------------- share fallback (ADR 0022) ------

@dataclass(frozen=True)
class ShareFallbackResult:
    """What the same clear would mean as shares, when no LEAP or spread fits
    the account (ADR 0022). Same scenarios, same robust Kelly and regime
    multiplier as §14; only the vehicle and its loss cap differ."""

    f_robust: float
    fraction_of_nav: float      # capital in the shares
    binding: str                # "kelly", "max_loss_cap" or "no_edge"
    dollars: float
    shares: float               # fractional, 4 dp
    whole_shares: int
    worst_move: float           # the worst scenario's price change, e.g. -0.30
    loss_at_worst: float        # dollars lost if that scenario plays out
    loss_at_worst_pct_nav: float
    review_price: float         # spot at the worst scenario: a §16 review trigger, never an automatic stop
    ev: float
    ev_to_el: float | None
    robust_log_growth: float    # E[log(1 + fraction*R)] at the chosen size
    passes_acceptance: bool     # §12.3's three tests, applied to the share returns


def share_fallback(cfg: dict, spot: float, probs: list[float], moves: list[float],
                   kelly_multiplier: float, nav: float, n_draws: int | None = None,
                   seed: int | None = None, existing_mechanism_loss_pct: float = 0.0,
                   existing_total_loss_pct: float = 0.0) -> ShareFallbackResult:
    """Size shares from the candidate's own §12.3 scenarios. `moves` are the
    underlying's price changes per scenario (−0.30 = −30%), the same ones the
    LEAP was priced on, so the share analysis can't use a rosier story.

    f_robust is the 10th-percentile Kelly fraction over posterior draws
    (§14), capped at 1.0 because shares here are never bought on margin.
    The position is min(kelly_multiplier × f_robust, the loss budget), where
    the budget is the smallest of three, all in % of NAV lost at the worst
    scenario: `max_loss_pct_nav` for this position, what's left of
    `max_loss_pct_nav_per_mechanism` after `existing_mechanism_loss_pct`, and
    what's left of `max_loss_pct_nav_total` after `existing_total_loss_pct`
    (see `existing_share_risk`). Clears cluster in a sector selloff, so the
    last two keep several correlated positions from stacking up.
    Acceptance is §12.3's: EV above `acceptance.ev_net_min`, EV/EL at least
    `acceptance.ev_to_expected_loss_min`, positive log growth."""
    if spot <= 0 or nav <= 0:
        raise ValueError("spot and NAV must be positive")
    draws = generate_posterior_draws(probs, moves, n_draws or get(cfg, "sizing.kelly_posterior_draws_min"), seed=seed)
    f_robust = robust_kelly_fraction(draws, f_cap=1.0, quantile=get(cfg, "sizing.f_robust_quantile"))
    worst = min(moves)
    ev = sum(p * m for p, m in zip(probs, moves))
    el = sum(p * max(0.0, -m) for p, m in zip(probs, moves))
    ev_to_el = ev / el if el > 0 else None
    budgets = {
        "max_loss_cap": get(cfg, "share_fallback.max_loss_pct_nav"),
        "mechanism_cap": get(cfg, "share_fallback.max_loss_pct_nav_per_mechanism") - existing_mechanism_loss_pct,
        "total_cap": get(cfg, "share_fallback.max_loss_pct_nav_total") - existing_total_loss_pct,
    }
    cap_name, budget_pct = min(budgets.items(), key=lambda kv: kv[1])
    if f_robust <= 0:
        fraction, binding = 0.0, "no_edge"
    elif budget_pct <= 0:
        fraction, binding = 0.0, cap_name
    else:
        kelly = kelly_multiplier * f_robust
        cap = (budget_pct / 100.0) / -worst if worst < 0 else 1.0
        fraction, binding = (kelly, "kelly") if kelly <= cap else (cap, cap_name)
    dollars = fraction * nav
    growth = _kelly_growth(fraction, probs, moves)
    passes = (
        ev > get(cfg, "acceptance.ev_net_min")
        and ev_to_el is not None and ev_to_el >= get(cfg, "acceptance.ev_to_expected_loss_min")
        and growth > get(cfg, "acceptance.robust_log_growth_min")
    )
    loss = dollars * max(0.0, -worst)
    return ShareFallbackResult(
        f_robust=f_robust, fraction_of_nav=fraction, binding=binding, dollars=round(dollars, 2),
        shares=round(dollars / spot, 4), whole_shares=math.floor(dollars / spot), worst_move=worst,
        loss_at_worst=round(loss, 2), loss_at_worst_pct_nav=loss / nav * 100.0,
        review_price=round(spot * (1 + worst), 2), ev=ev, ev_to_el=ev_to_el,
        robust_log_growth=growth, passes_acceptance=passes,
    )


def existing_share_risk(holdings: dict[str, float], watchlist_names: list[dict],
                        ledger_entries: list[dict], cfg: dict, nav: float) -> dict:
    """The share risk already on, for share_fallback's mechanism and total caps.

    `holdings` maps symbol to market value from the configured account's
    `get_equity_positions`. Only watchlist names count: the caps govern this
    system's ideas, not the rest of the account. Each holding's loss is its
    value times its worst move: the one on its open ledger entry's
    `share_fallback` block if there is one, else
    `share_fallback.held_worst_move_pct` [ASSUMPTION]. Returns % of NAV lost
    at the worst case, per mechanism and in total."""
    mech = {n["ticker"]: n.get("mechanism") for n in watchlist_names}
    worst = {}
    for e in ledger_entries:
        fb = e.get("share_fallback") or {}
        if e.get("realized_outcome") is None and not e.get("duplicate_of") and fb.get("worst_move") is not None:
            worst[e["ticker"]] = fb["worst_move"]
    default = -get(cfg, "share_fallback.held_worst_move_pct") / 100.0
    by_mech: dict[str, float] = {}
    total = 0.0
    for sym, value in holdings.items():
        if sym not in mech or value <= 0:
            continue
        loss_pct = value * -worst.get(sym, default) / nav * 100.0
        by_mech[mech[sym]] = by_mech.get(mech[sym], 0.0) + loss_pct
        total += loss_pct
    return {"by_mechanism": by_mech, "total": total}
