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
from datetime import date as _date
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


# ----------------------------------------- staleness clocks (ADR 0018) -----
#
# Two different questions, previously conflated into one date. "Has anyone
# refreshed lately?" is answered by the last macro-refresh RUN. "Is a source
# silently frozen?" is answered per series against its own publication cadence.
# Measuring the first against the data's `as_of` flagged stale every Thursday:
# `as_of` is the oldest latest-print across all series, and WALCL is weekly
# (dated Wednesday, published Thursday), so it is already days old the moment a
# Sunday refresh finishes. Observed firing 2026-09-17 with a 2026-09-14 refresh.

@dataclass(frozen=True)
class StalenessResult:
    days: int
    band: str  # "current" | "flag" | "stop"
    basis: str


def macro_staleness(last_refreshed: str, today: str, cfg: dict) -> StalenessResult:
    """Age of the macro state in calendar days since the last successful
    `macro-refresh` run, and which of §1a's three bands that falls in."""
    days = (_date.fromisoformat(today) - _date.fromisoformat(last_refreshed)).days
    if days > get(cfg, "macro_staleness.stop_after_days"):
        band = "stop"
    elif days > get(cfg, "macro_staleness.flag_after_days"):
        band = "flag"
    else:
        band = "current"
    return StalenessResult(days, band, last_refreshed)


@dataclass(frozen=True)
class SourceLagResult:
    stale: list[tuple[str, int, int]]  # (series, days behind, limit)
    unconfigured: list[str]

    @property
    def ok(self) -> bool:
        return not self.stale and not self.unconfigured


def stale_sources(latest_by_series: dict[str, str], today: str, cfg: dict) -> SourceLagResult:
    """Which fetched series are further behind than their own publication
    cadence allows — the guard that stops a fresh run date from vouching for a
    series FRED has stopped updating."""
    cadence = get(cfg, "macro_staleness.source_cadence") or {}
    limits = get(cfg, "macro_staleness.max_source_lag_days") or {}
    stale, unconfigured = [], []
    for series, latest in sorted(latest_by_series.items()):
        if series not in cadence:
            unconfigured.append(series)
            continue
        limit = limits[cadence[series]]
        days = (_date.fromisoformat(today) - _date.fromisoformat(latest)).days
        if days > limit:
            stale.append((series, days, limit))
    return SourceLagResult(stale, unconfigured)


# ------------------------------------- daily replay for gates 1 & 2 (ADR 0017) ---
#
# Gates 1 and 2 are refreshed by a weekly desktop job, but release_consecutive_closes
# counts trading-day closes. Stepping once per run made a 5-close release take 5
# weeks, let a trigger that fired and faded between runs go unseen, and advanced
# the streak again on every same-day re-run. Each run now replays every
# observation since the last one it processed, using that day's own inputs.

DailyCondition = tuple[str, bool, bool]


def credit_stress_daily(hy_oas: Sequence[tuple[str, float]], cfg: dict, lookback: int = 20) -> list[DailyCondition]:
    """(date, triggered, release_met) for each HY OAS observation that has
    `lookback` observations before it, oldest first."""
    s = sorted(hy_oas)
    return [
        (s[i][0], credit_stress_trigger(s[i][1], s[i - lookback][1], cfg), credit_stress_release_met(s[i][1], cfg))
        for i in range(lookback, len(s))
    ]


def inflation_shock_daily(
    real10: Sequence[tuple[str, float]],
    nominal10: Sequence[tuple[str, float]],
    breakeven_5y5y: Sequence[tuple[str, float]],
    cfg: dict,
    lookback: int = 10,
) -> list[DailyCondition]:
    """(date, triggered, release_met) for each date all three series report.
    Each delta is taken within its own series, `lookback` observations back, so
    a day one series skips doesn't shift the others' windows."""
    series = [sorted(real10), sorted(nominal10), sorted(breakeven_5y5y)]
    index = [{d: i for i, (d, _) in enumerate(s)} for s in series]
    common = sorted(set(index[0]) & set(index[1]) & set(index[2]))
    out = []
    for d in common:
        pos = [idx[d] for idx in index]
        if min(pos) < lookback:
            continue
        deltas = [s[p][1] - s[p - lookback][1] for s, p in zip(series, pos)]
        out.append((d, inflation_shock_trigger(*deltas, cfg), inflation_shock_release_met(*deltas, cfg)))
    return out


def advance_hard_gate(
    prev: HardGateState | None,
    daily: Sequence[DailyCondition],
    after: str,
    release_streak_required: int,
) -> tuple[HardGateState, str, int]:
    """Step `prev` once for every observation dated strictly after `after`.

    Returns (state, new_cursor, steps). Idempotent: re-running with the returned
    cursor steps zero times, so a second refresh on the same day can't advance
    the release streak twice."""
    state = prev or HardGateState(active=False)
    cursor, steps = after, 0
    for d, triggered, release_met in sorted(daily):
        if d <= after:
            continue
        state = step_hard_gate(state, triggered, release_met, release_streak_required)
        cursor, steps = d, steps + 1
    return state, cursor, steps


# --------------------------------------------- gate 3: equity deleveraging ---

def spx_pct_vs_200dma(closes: Sequence[float], window: int = 200) -> float:
    """Signed % of the latest close relative to its trailing `window`-close
    mean: NEGATIVE when below the average, e.g. -11.0 means 11% below.

    This is the exact value `equity_deleveraging_trigger`'s
    `spx_pct_below_200dma` parameter expects. That parameter's name reads like
    a positive magnitude, and computing `(mean - close) / mean` — the natural
    reading of "percent below" — inverts the sign so a real 12% drawdown
    arrives as +12 and the gate never fires. Found 2026-09-14 in a manual
    macro-refresh that had done exactly that; always call this instead of
    deriving the value in prose.

    `closes` is oldest-first and must include the latest close as its last
    element."""
    if len(closes) < window:
        raise ValueError(f"need at least {window} closes, got {len(closes)}")
    mean = sum(closes[-window:]) / window
    return (closes[-1] - mean) / mean * 100.0


def equity_deleveraging_escalated(
    vix_now: float, vix_prev: float, spx_pct_below_200dma: float, cfg: dict
) -> bool:
    """True when VIX and the S&P both already fire — the only state in which
    the trigger consults breadth at all."""
    g = "macro_hard_gates.equity_deleveraging."
    vix_fires = vix_now >= get(cfg, g + "vix_level") and vix_prev >= get(cfg, g + "vix_level")
    spx_fires = spx_pct_below_200dma <= -get(cfg, g + "spx_pct_below_200dma")
    return vix_fires and spx_fires


def breadth_needed(
    vix_now: float,
    vix_prev: float,
    spx_pct_below_200dma: float,
    gate_active: bool,
    cfg: dict,
) -> bool:
    """Whether this session must compute breadth: the trigger reads it only
    when escalated, and the release check reads it only while the gate is
    active. Every other session can skip the NYSE-wide pull entirely without
    changing any gate outcome (ADR 0016)."""
    return gate_active or equity_deleveraging_escalated(vix_now, vix_prev, spx_pct_below_200dma, cfg)


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
    if not equity_deleveraging_escalated(vix_now, vix_prev, spx_pct_below_200dma, cfg):
        return False
    if breadth_pct_above_200dma is None:
        return True
    return breadth_pct_above_200dma < get(
        cfg, "macro_hard_gates.equity_deleveraging.breadth_pct_above_200dma"
    )


@dataclass(frozen=True)
class BreadthResult:
    """% of the universe above its own trailing-200-close mean, or a stated
    reason it could not be computed. Callers pass `pct_above_200dma` to the
    gate functions, which already treat `None` as fail-closed."""

    available: bool
    pct_above_200dma: float | None
    as_of: str | None
    universe_size: int
    names_on_date: int
    names_computed: int
    names_short_history: int
    coverage: float
    reason: str | None = None


def compute_breadth(
    closes_by_symbol: dict[str, Sequence[tuple[str, float]]],
    universe: Sequence[str],
    cfg: dict,
    window: int = 200,
) -> BreadthResult:
    """§6.1 NYSE breadth over `universe`, each symbol's (date, close) pairs
    oldest-first.

    The reference date is the most common latest-bar date across the
    universe. Symbols whose feed ends on a different date are treated as
    missing rather than mixed in — a lagging feed (a full-session stall in
    Robinhood's daily bars was observed 2026-09-08) would otherwise blend
    two sessions into one reading.

    Coverage is measured on data retrieval (symbols present on the reference
    date / universe size), not on history length: a recent listing without
    200 closes is structurally uncomputable, not a data failure, so it is
    counted in `names_short_history` and excluded without penalizing
    coverage."""
    universe_size = len(universe)
    last_dates = {
        s: closes_by_symbol[s][-1][0] for s in universe if closes_by_symbol.get(s)
    }
    if not last_dates:
        return BreadthResult(False, None, None, universe_size, 0, 0, 0, 0.0,
                             reason="no symbol in the universe returned data")

    counts: dict[str, int] = {}
    for d in last_dates.values():
        counts[d] = counts.get(d, 0) + 1
    as_of = max(counts, key=lambda d: (counts[d], d))

    on_date = [s for s, d in last_dates.items() if d == as_of]
    coverage = len(on_date) / universe_size
    floor = get(cfg, "macro_hard_gates.equity_deleveraging.breadth_min_coverage")
    if coverage < floor:
        return BreadthResult(False, None, as_of, universe_size, len(on_date), 0, 0, coverage,
                             reason=f"coverage {coverage:.1%} below the {floor:.0%} floor")

    above = computed = short = 0
    for s in on_date:
        closes = [c for _, c in closes_by_symbol[s]]
        if len(closes) < window:
            short += 1
            continue
        computed += 1
        if closes[-1] > sum(closes[-window:]) / window:
            above += 1
    if not computed:
        return BreadthResult(False, None, as_of, universe_size, len(on_date), 0, short, coverage,
                             reason=f"no symbol had {window} closes")
    return BreadthResult(True, above / computed * 100.0, as_of, universe_size,
                         len(on_date), computed, short, coverage)


# ----------------------------------------- credit early warning (ADR 0017) -----

@dataclass(frozen=True)
class CreditProxyResult:
    """A daily early warning for §6.1's credit gate, which is only refreshed
    weekly. Never a gate: it can prompt a human to run macro-refresh, but it
    must not block or approve anything on its own."""

    available: bool
    tripped: bool
    drawdown_pct: float | None
    as_of: str | None
    reason: str | None = None


def credit_proxy_check(
    credit_closes: Sequence[tuple[str, float]],
    hedge_closes: Sequence[tuple[str, float]],
    cfg: dict,
) -> CreditProxyResult:
    """How far the high-yield/short-Treasury price ratio sits below its high
    over the trailing `lookback_sessions`.

    The ratio, not the credit ETF alone: calibrated on 2025-09..2026-09, raw
    HYG correlated 0.47 with 10Y yield changes and read 1.65% off its high on
    2026-09-11 while HY OAS had tightened 6bp — a rates move posing as credit
    stress. Dividing by SHY cut that to 0.24 and lifted correlation with HY OAS
    changes from 0.54 to 0.74. SHY is deliberately short: a duration-matched
    hedge over-corrects (HYG/IEI went negative, -0.40), which would understate a
    shock where yields and spreads rise together."""
    g = "tripwires.credit_proxy."
    lookback = get(cfg, g + "lookback_sessions")
    hedge = dict(hedge_closes)
    ratio = [(d, c / hedge[d]) for d, c in sorted(credit_closes) if hedge.get(d)]
    if len(ratio) <= lookback:
        return CreditProxyResult(False, False, None, ratio[-1][0] if ratio else None,
                                 reason=f"need {lookback + 1} aligned sessions, got {len(ratio)}")
    window = [v for _, v in ratio[-(lookback + 1):]]
    drawdown = (max(window) - window[-1]) / max(window) * 100.0
    return CreditProxyResult(True, drawdown >= get(cfg, g + "drawdown_pct"), drawdown, ratio[-1][0])


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
