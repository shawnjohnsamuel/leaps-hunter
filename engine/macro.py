"""§6 macro layer — hard disqualifiers (§6.1) and the restricted-regime
throttle (§6.2). ADR 0001: macro is a gate and a throttle, never additive
points. ADR 0012 amends §6.1's equity-deleveraging gate: breadth is an
escalation input, consulted only once VIX and S&P conditions both already
hold, and unknown breadth fails CLOSED — on the trigger side (can't rule out
a systemic gate on missing data) and, symmetrically, on the release side
(can't confirm a release on missing data either).

Hard-gate state is a one-step transition (`step_hard_gate`), not a full
historical replay. FRED gives deep history for the credit and inflation
series, but breadth has no historical series at all — it only starts
accumulating the day the desktop job first runs (ADR 0012) — so all three
gates use the same incremental design for consistency. The daily routine is
expected to persist each gate's `HardGateState` in state/macro-latest.json
(Phase 4) and pass yesterday's state back in here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .config import get


def _bp(basis_points: float) -> float:
    """Convert a basis-point threshold from §20's config into the
    percentage-point units FRED's rate/spread series are quoted in."""
    return basis_points / 100.0


# ------------------------------------------------------ hard-gate state -----

@dataclass(frozen=True)
class HardGateState:
    active: bool
    consecutive_release_days: int = 0


def step_hard_gate(
    prev: HardGateState | None,
    triggered_today: bool,
    release_condition_met_today: bool | None,
    release_streak_required: int,
) -> HardGateState:
    """One day's transition for any §6.1 hard gate.

    `release_condition_met_today` is None when a required release-side input
    (e.g. breadth) was unavailable — treated as NOT met, i.e. fails closed
    (ADR 0012), symmetric with the trigger side's fail-closed rule.
    """
    prev_active = prev.active if prev else False
    if not prev_active:
        return (
            HardGateState(active=True, consecutive_release_days=0)
            if triggered_today
            else HardGateState(active=False, consecutive_release_days=0)
        )

    prev_streak = prev.consecutive_release_days if prev else 0
    streak = prev_streak + 1 if release_condition_met_today else 0
    if streak >= release_streak_required:
        return HardGateState(active=False, consecutive_release_days=0)
    return HardGateState(active=True, consecutive_release_days=streak)


# -------------------------------------------------- gate 1: credit stress -----

def credit_stress_trigger(oas_now_pct: float, oas_20d_ago_pct: float, cfg: dict) -> bool:
    g = "macro_hard_gates.credit_stress."
    absolute = _bp(get(cfg, g + "hy_oas_bp_absolute"))
    widen = _bp(get(cfg, g + "hy_oas_bp_widening_20d"))
    floor = _bp(get(cfg, g + "hy_oas_bp_widening_floor"))
    widened = (oas_now_pct - oas_20d_ago_pct) >= widen and oas_now_pct > floor
    return oas_now_pct >= absolute or widened


def credit_stress_release_met(oas_now_pct: float, cfg: dict) -> bool:
    """[ASSUMPTION]: §20 gives two trigger thresholds (absolute, widening
    floor) but §6.1's release column says only "below both applicable
    thresholds," without stating which value governs the widening
    condition's release check. Being below the LOWER (widening-floor)
    threshold implies being below the absolute one too, so that single,
    more conservative check is used here.
    """
    floor = _bp(get(cfg, "macro_hard_gates.credit_stress.hy_oas_bp_widening_floor"))
    return oas_now_pct < floor


# --------------------------------------------- gate 2: inflation-duration -----

def inflation_shock_trigger(
    real10_delta_10d: float, nominal10_delta_10d: float, breakeven_delta_10d: float, cfg: dict
) -> bool:
    g = "macro_hard_gates.inflation_duration_shock."
    return (
        real10_delta_10d >= _bp(get(cfg, g + "real_10y_bp_10d"))
        and nominal10_delta_10d >= _bp(get(cfg, g + "nominal_10y_bp_10d"))
        and breakeven_delta_10d >= _bp(get(cfg, g + "breakeven_5y5y_bp_10d"))
    )


def inflation_shock_release_met(
    real10_delta_10d: float, nominal10_delta_10d: float, breakeven_delta_10d: float, cfg: dict
) -> bool:
    g = "macro_hard_gates.inflation_duration_shock."
    frac = get(cfg, g + "release_fraction_of_trigger")
    return (
        real10_delta_10d < _bp(get(cfg, g + "real_10y_bp_10d")) * frac
        and nominal10_delta_10d < _bp(get(cfg, g + "nominal_10y_bp_10d")) * frac
        and breakeven_delta_10d < _bp(get(cfg, g + "breakeven_5y5y_bp_10d")) * frac
    )


# --------------------------------------------- gate 3: equity deleveraging ---

def equity_deleveraging_trigger(
    vix_now: float,
    vix_prev: float,
    spx_pct_below_200dma: float,
    breadth_pct_above_200dma: float | None,
    cfg: dict,
) -> bool:
    """Breadth is an escalation input (ADR 0012): only consulted once VIX
    and S&P both already fire. If those two hold and breadth is
    unavailable, the gate is treated as TRIGGERED (fail closed) rather than
    left unresolved — the cost of a false positive here is a day without
    new positions, which §0 already calls a successful session."""
    g = "macro_hard_gates.equity_deleveraging."
    vix_fires = vix_now >= get(cfg, g + "vix_level") and vix_prev >= get(cfg, g + "vix_level")
    spx_fires = spx_pct_below_200dma <= -get(cfg, g + "spx_pct_below_200dma")
    if not (vix_fires and spx_fires):
        return False
    if breadth_pct_above_200dma is None:
        return True
    return breadth_pct_above_200dma < get(cfg, g + "breadth_pct_above_200dma")


def equity_deleveraging_release_met(
    vix_now: float, breadth_pct_above_200dma: float | None, cfg: dict
) -> bool:
    """Symmetric fail-closed: unavailable breadth cannot confirm a release,
    so the gate stays active rather than lapsing on missing data."""
    g = "macro_hard_gates.equity_deleveraging."
    if breadth_pct_above_200dma is None:
        return False
    return vix_now < get(cfg, g + "release_vix_below") and breadth_pct_above_200dma > get(
        cfg, g + "release_breadth_above"
    )


# -------------------------------------------------------- §6.2 R throttle ----

def percentile_rank(history: Sequence[float], value: float) -> float:
    """% of `history` strictly below `value`. §6.2: recomputed weekly
    against the longest reliable published history, never hardcoded."""
    if not history:
        raise ValueError("empty history")
    return sum(1 for v in history if v < value) / len(history) * 100.0


def net_liquidity_series(
    walcl: Sequence[tuple[str, float]],
    wtregen: Sequence[tuple[str, float]],
    rrp_bn: Sequence[tuple[str, float]],
) -> list[tuple[str, float]]:
    """WALCL − TGA − (RRP in $bn × 1000), aligned on WALCL's (weekly) dates
    using the most recent TGA/RRP observation on or before each date. WALCL
    and TGA are $mm; RRP is $bn per FRED's native units."""
    tga_map, rrp_map = dict(wtregen), dict(rrp_bn)
    tga_dates, rrp_dates = sorted(tga_map), sorted(rrp_map)

    def _nearest(dates_sorted, mapping, as_of):
        candidates = [d for d in dates_sorted if d <= as_of]
        return mapping[candidates[-1]] if candidates else None

    out = []
    for d, w in sorted(walcl):
        tga = _nearest(tga_dates, tga_map, d)
        rrp = _nearest(rrp_dates, rrp_map, d)
        if tga is None or rrp is None:
            continue
        out.append((d, w - tga - rrp * 1000))
    return out


def net_liquidity_contracting(series: Sequence[tuple[str, float]], lookback_periods: int = 13) -> bool:
    """True if the latest reading is below the reading `lookback_periods`
    observations back. WALCL is weekly, so the validated default of 13
    periods is roughly one quarter."""
    if len(series) <= lookback_periods:
        raise ValueError(f"need more than {lookback_periods} observations, got {len(series)}")
    return series[-1][1] < series[-1 - lookback_periods][1]


@dataclass(frozen=True)
class RestrictedRegimeResult:
    R: int
    components: dict[str, bool]
    restricted: bool
    score_threshold: int
    kelly_multiplier: float


def compute_restricted_regime(
    cfg: dict,
    cape_now: float,
    cape_history: Sequence[float],
    credit_now: float,
    credit_history: Sequence[float],
    real30_now: float,
    real30_history: Sequence[float],
    liquidity_contracting: bool,
) -> RestrictedRegimeResult:
    """§6.2: R = sum of four 0/1 components. `credit_now`/`credit_history`
    should be BAA10Y, not the HY OAS series used by the §6.1 gate — FRED
    caps ICE BofA history at ~3 years regardless of an API key (confirmed
    2026-09-03), which is too short to support a 20th-percentile claim
    (ADR 0011)."""
    components = {
        "cape_gt_95pct": percentile_rank(cape_history, cape_now) > 95,
        "hy_oas_lt_20pct": percentile_rank(credit_history, credit_now) < 20,
        "real_30y_gt_90pct": percentile_rank(real30_history, real30_now) > 90,
        "net_liquidity_contracting": liquidity_contracting,
    }
    R = sum(components.values())
    restricted = R >= get(cfg, "restricted_regime.trigger_R")
    key = "restricted_regime.score_threshold_" + ("restricted" if restricted else "normal")
    mult_key = "restricted_regime.kelly_multiplier_" + ("restricted" if restricted else "normal")
    return RestrictedRegimeResult(
        R=R,
        components=components,
        restricted=restricted,
        score_threshold=get(cfg, key),
        kelly_multiplier=get(cfg, mult_key),
    )
