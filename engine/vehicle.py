"""stock-screen's deterministic half (ADR 0019): name-level hard
disqualifiers, per-vehicle gates, factor scoring, and the deep-dive scenario
math for four vehicles — shares, a short-dated call, a cash-secured put, and
a LEAP.

The skill answers a question v7 deliberately doesn't ask: for any stock or
ETF, which vehicle fits, and how does the name rank against others. ADR
0010's split still applies. The model gathers evidence and makes the six
calls in `JudgedFactors`; everything that can be arithmetic is arithmetic
here, so the same inputs always produce the same score, and names screened
on different days rank against each other honestly.

Two configs, on purpose. `engine/stock_screen.yaml` holds every stock-screen
threshold and weight. The LEAP row reads v7's config instead (DTE band,
spread, open interest, the §13.1 delta policy), so stock-screen can never
call a LEAP permissible that bench-check or daily-screen would reject. The
LEAP row is never sized here: v7 owns LEAP sizing.

Fail-closed like the rest of the engine: a missing input never passes a
gate, and a missing factor is bounded at 0 and 10 instead of guessed. The
floor is what ranks; the gap between floor and ceiling sets the confidence.
That is the same bounding daily-screen used on 2026-09-03 for an unpriced
§11 dimension.

CLI (JSON in, JSON out) so the skill never re-derives this arithmetic:
    python3 -m engine.vehicle technicals <historicals.json>
    python3 -m engine.vehicle strike --spot S --delta 0.70 --dte 60 --iv 0.45 [--put]
    python3 -m engine.vehicle screen --v7-config C --macro M --watchlist W a.json [b.json ...]
    python3 -m engine.vehicle deep-dive --v7-config C --macro M a.json
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from . import yaml_lite
from .config import get, load_config
from .gates import GateCheck, catalyst_duration_gate, dte_gate, open_interest_gate, spread_gate
from .macro import macro_staleness
from .optmodel import bs_call_price, evaluate_delta_policy, executable_entry
from .priceseries import realized_vol, rolling_max, rsi_wilder, sma
from .sizing import _kelly_growth, kelly_f_star

CONFIG_PATH = Path(__file__).parent / "stock_screen.yaml"

VEHICLES = ("shares", "short_call", "csp", "leap")
OPTION_VEHICLES = ("short_call", "csp", "leap")
JUDGED = (
    "fundamental_quality", "valuation_dislocation", "catalyst_strength",
    "downside_survivability", "technical_setup", "sentiment_positioning",
)


def load_screen_config(path=CONFIG_PATH) -> dict:
    return yaml_lite.load(Path(path).read_text())


def _clamp(x: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, x))


def _round_half_up(x: float) -> int:
    """Python's round() is banker's rounding; a 64.5 should not rank by
    whether 64 happens to be even."""
    return int(math.floor(x + 0.5))


# ----------------------------------------------------- name disqualifiers --

@dataclass(frozen=True)
class NameInputs:
    """Facts behind the name-level hard disqualifiers. `None` means the
    skill could not establish the fact, and the check fails rather than
    passes. `integrity_red_flag` covers fraud allegations, a delisting
    notice, a pending restatement, or an auditor's going-concern doubt.
    `dilution_from_acquisition` is True only when the share-count jump comes
    from one closed, stock-funded acquisition rather than ongoing issuance.
    For a closed-end fund, `aum_usd` is net assets (NAV x shares), never
    market cap, and `last_price` / `nav_per_share` / `nav_age_days` give the
    premium to NAV and how much to trust it."""

    instrument_type: str  # "stock", "etf" or "cef" (closed-end fund)
    avg_daily_dollar_volume: float | None = None
    fcf_positive: bool | None = None
    cash_runway_months: float | None = None
    funding_secured: bool | None = None
    share_count_growth_yoy_pct: float | None = None
    revenue_growth_yoy_pct: float | None = None
    prior_year_quarter_revenue_usd: float | None = None
    integrity_red_flag: bool | None = None
    dilution_from_acquisition: bool | None = None
    leveraged_or_inverse: bool | None = None
    aum_usd: float | None = None
    expense_ratio_pct: float | None = None
    last_price: float | None = None
    nav_per_share: float | None = None
    nav_age_days: int | None = None


def _dollar_volume_check(cfg: dict, adv: float | None) -> GateCheck:
    floor = get(cfg, "disqualifiers.min_avg_daily_dollar_volume")
    if adv is None:
        return GateCheck("dollar_volume", False, "average daily dollar volume unknown")
    return GateCheck("dollar_volume", adv >= floor, f"${adv:,.0f}/day (min ${floor:,.0f})")


def _runway_check(cfg: dict, n: NameInputs) -> GateCheck:
    if n.fcf_positive is None:
        return GateCheck("cash_runway", False, "free-cash-flow sign not established")
    if n.fcf_positive:
        return GateCheck("cash_runway", True, "free cash flow positive")
    if n.funding_secured:
        return GateCheck("cash_runway", True, "burning cash, funding secured")
    minimum = get(cfg, "disqualifiers.min_cash_runway_months")
    if n.cash_runway_months is None:
        return GateCheck("cash_runway", False, "burning cash and runway unknown")
    return GateCheck(
        "cash_runway", n.cash_runway_months >= minimum,
        f"{n.cash_runway_months:.0f} months of runway (min {minimum})",
    )


def _dilution_check(cfg: dict, n: NameInputs) -> GateCheck:
    maximum = get(cfg, "disqualifiers.max_share_growth_yoy_pct")
    multiple = get(cfg, "disqualifiers.dilution_growth_offset_multiple")
    g = n.share_count_growth_yoy_pct
    if g is None:
        return GateCheck("dilution", False, "share-count trend not established")
    if g <= maximum:
        return GateCheck("dilution", True, f"share count {g:+.1f}% YoY (max {maximum}%)")
    # The rule targets ongoing issuance that funds operations. A single
    # stock-funded acquisition is a step change, not a habit (CEG/Calpine,
    # 2026-09-21), so it passes and the reason says why.
    if n.dilution_from_acquisition:
        return GateCheck("dilution", True, f"share count {g:+.1f}% YoY from a one-time stock-funded acquisition")
    if n.revenue_growth_yoy_pct is None:
        return GateCheck("dilution", False, f"share count {g:+.1f}% YoY, revenue growth unknown")
    min_base = get(cfg, "disqualifiers.dilution_offset_min_prior_quarter_revenue_usd")
    base = n.prior_year_quarter_revenue_usd
    if base is None or base < min_base:
        shown = "unknown" if base is None else f"${base:,.0f}"
        return GateCheck(
            "dilution", False,
            f"share count {g:+.1f}% YoY; revenue growth can't offset it from a {shown} "
            f"prior-year quarter (needs >= ${min_base:,.0f})",
        )
    return GateCheck(
        "dilution", n.revenue_growth_yoy_pct >= multiple * g,
        f"share count {g:+.1f}% YoY vs revenue {n.revenue_growth_yoy_pct:+.1f}% "
        f"(dilution over {maximum}% needs revenue growth >= {multiple}x it)",
    )


def _flag_check(name: str, flag: bool | None, bad: str, good: str) -> GateCheck:
    if flag is None:
        return GateCheck(name, False, "not assessed")
    return GateCheck(name, not flag, bad if flag else good)


def premium_to_nav_pct(n: NameInputs) -> float | None:
    if n.last_price is None or not n.nav_per_share:
        return None
    return (n.last_price / n.nav_per_share - 1) * 100


def _cef_checks(cfg: dict, n: NameInputs) -> list[GateCheck]:
    d = get(cfg, "disqualifiers")
    checks = []
    min_assets = d["cef_min_net_assets_usd"]
    checks.append(GateCheck("net_assets", False, "net assets unknown") if n.aum_usd is None else
                  GateCheck("net_assets", n.aum_usd >= min_assets,
                            f"${n.aum_usd:,.0f} (min ${min_assets:,.0f})"))
    er_max = d["cef_max_expense_ratio_pct"]
    checks.append(GateCheck("expense_ratio", False, "expense ratio unknown") if n.expense_ratio_pct is None else
                  GateCheck("expense_ratio", n.expense_ratio_pct <= er_max,
                            f"{n.expense_ratio_pct:.2f}% (max {er_max}% for a closed-end fund)"))
    max_age = d["cef_max_nav_age_days"]
    if n.nav_age_days is None:
        checks.append(GateCheck("nav_age", False, "NAV date unknown"))
    else:
        checks.append(GateCheck("nav_age", n.nav_age_days <= max_age,
                                f"NAV is {n.nav_age_days}d old (max {max_age}d)"))
    prem = premium_to_nav_pct(n)
    max_prem = d["cef_max_premium_to_nav_pct"]
    if prem is None:
        checks.append(GateCheck("premium_to_nav", False, "price or NAV per share unknown"))
    else:
        side = "premium" if prem >= 0 else "discount"
        checks.append(GateCheck("premium_to_nav", prem <= max_prem,
                                f"{abs(prem):.1f}% {side} to NAV (max premium {max_prem}%)"))
    checks.append(_flag_check("integrity", n.integrity_red_flag,
                              "fraud, regulator action, restatement or valuation-agent flag", "no integrity flags"))
    return checks


def name_disqualifiers(cfg: dict, n: NameInputs) -> list[GateCheck]:
    if n.instrument_type not in ("stock", "etf", "cef"):
        return [GateCheck("instrument_type", False, f"unknown instrument type {n.instrument_type!r}")]
    checks = [_dollar_volume_check(cfg, n.avg_daily_dollar_volume)]
    if n.instrument_type == "stock":
        checks += [
            _runway_check(cfg, n),
            _dilution_check(cfg, n),
            _flag_check("integrity", n.integrity_red_flag,
                        "fraud, delisting, restatement or going-concern flag", "no integrity flags"),
        ]
    elif n.instrument_type == "cef":
        checks += _cef_checks(cfg, n)
    else:
        # Daily-reset leverage decays over any holding period this skill
        # screens for (30+ days), so it fails every vehicle, not just some.
        checks.append(_flag_check("leveraged_or_inverse", n.leveraged_or_inverse,
                                  "leveraged or inverse daily-reset ETF", "unleveraged"))
        aum_min = get(cfg, "disqualifiers.etf_min_aum_usd")
        er_max = get(cfg, "disqualifiers.etf_max_expense_ratio_pct")
        checks.append(GateCheck("aum", False, "AUM unknown") if n.aum_usd is None else
                      GateCheck("aum", n.aum_usd >= aum_min, f"${n.aum_usd:,.0f} (min ${aum_min:,.0f})"))
        checks.append(GateCheck("expense_ratio", False, "expense ratio unknown") if n.expense_ratio_pct is None else
                      GateCheck("expense_ratio", n.expense_ratio_pct <= er_max,
                                f"{n.expense_ratio_pct:.2f}% (max {er_max}%)"))
    return checks


# ------------------------------------------------------------- factors ----

@dataclass(frozen=True)
class JudgedFactors:
    """The six calls only the model can make, each 0-10 against the rubric
    in the skill's references/scoring.md. `None` means the evidence to make
    the call wasn't found; it is bounded, never guessed."""

    fundamental_quality: float | None = None
    valuation_dislocation: float | None = None
    catalyst_strength: float | None = None
    downside_survivability: float | None = None
    technical_setup: float | None = None
    sentiment_positioning: float | None = None


@dataclass(frozen=True)
class MarketInputs:
    """Computed from data, never judged. `technicals` (CLI: `technicals`)
    turns closes and Robinhood's indicator values into rsi14,
    pct_above_50dma and hv30 (with its largest move trimmed, per config)."""

    rsi14: float | None = None
    pct_above_50dma: float | None = None
    hv30: float | None = None           # annualized realized vol, as a fraction
    atm_iv: float | None = None         # ~30-60 DTE at-the-money implied vol, as a fraction
    iv_rank: float | None = None        # 0-100, only when a source actually reports it
    days_to_earnings: int | None = None
    days_to_nearest_catalyst: int | None = None

    @property
    def iv_hv_ratio(self) -> float | None:
        if self.atm_iv is None or not self.hv30:
            return None
        return self.atm_iv / self.hv30


def volatility_pricing_score(cfg: dict, m: MarketInputs) -> float | None:
    """10 = options cheap, 0 = expensive. IV rank when a source reports it;
    otherwise ATM IV against 30-day realized vol, which is always computable
    from a chain snapshot and a year of closes."""
    if m.iv_rank is not None:
        return _clamp(10.0 - m.iv_rank / 10.0)
    ratio = m.iv_hv_ratio
    if ratio is None:
        return None
    cheap = get(cfg, "factors.volatility_pricing.iv_hv_cheap_at_or_below")
    rich = get(cfg, "factors.volatility_pricing.iv_hv_rich_at_or_above")
    return _clamp(10.0 * (rich - ratio) / (rich - cheap))


@dataclass(frozen=True)
class FactorBounds:
    floor: dict[str, float]
    ceiling: dict[str, float]
    notes: list[str]


def factor_bounds(cfg: dict, judged: JudgedFactors, market: MarketInputs) -> FactorBounds:
    floor: dict[str, float] = {}
    ceiling: dict[str, float] = {}
    notes: list[str] = []
    for name in JUDGED:
        v = getattr(judged, name)
        if v is None:
            floor[name], ceiling[name] = 0.0, 10.0
            notes.append(f"{name} not assessed: bounded [0, 10]")
        elif not 0 <= v <= 10:
            raise ValueError(f"{name}={v} is outside 0-10")
        else:
            floor[name] = ceiling[name] = float(v)

    cap_cfg = get(cfg, "factors.extension_cap")
    cap = float(cap_cfg["capped_score"])
    readings = [
        (market.rsi14, cap_cfg["rsi14_at_or_above"], "RSI14"),
        (market.pct_above_50dma, cap_cfg["pct_above_50dma_at_or_above"], "% above 50DMA"),
    ]
    extended = [f"{label} {v:.1f} >= {thr}" for v, thr, label in readings if v is not None and v >= thr]
    if not extended and all(v is not None for v, _, _ in readings):
        notes.append("extension cap not applied: " + "; ".join(f"{label} {v:.1f} < {thr}" for v, thr, label in readings))
    if extended:
        floor["technical_setup"] = min(floor["technical_setup"], cap)
        ceiling["technical_setup"] = min(ceiling["technical_setup"], cap)
        notes.append(f"technical_setup capped at {cap:g}: extended ({'; '.join(extended)})")
    elif any(v is None for v, _, _ in readings):
        floor["technical_setup"] = min(floor["technical_setup"], cap)
        notes.append(f"extension unverified: technical_setup floor capped at {cap:g}")

    vol = volatility_pricing_score(cfg, market)
    if vol is None:
        floor["volatility_pricing"], ceiling["volatility_pricing"] = 0.0, 10.0
        notes.append("no IV rank or IV/HV ratio: volatility_pricing bounded [0, 10]")
    else:
        floor["volatility_pricing"] = ceiling["volatility_pricing"] = vol
        basis = f"IV rank {market.iv_rank:.0f}" if market.iv_rank is not None else f"ATM IV / HV30 {market.iv_hv_ratio:.2f}"
        notes.append(f"volatility_pricing {vol:.1f}/10 from {basis}")
    floor["iv_richness"] = 10.0 - ceiling["volatility_pricing"]
    ceiling["iv_richness"] = 10.0 - floor["volatility_pricing"]
    return FactorBounds(floor, ceiling, notes)


def _weighted(cfg: dict, vehicle: str, factors: dict[str, float]) -> float:
    return 10.0 * sum(w * factors[k] for k, w in get(cfg, f"weights.{vehicle}").items())


# ------------------------------------------------------ vehicle gates -----

@dataclass(frozen=True)
class ContractQuote:
    """One live contract the skill picked for an option vehicle. `delta` is
    an absolute value: a 0.25-delta put is 0.25."""

    expiration: str
    dte_days: int
    strike: float
    delta: float
    bid: float
    ask: float
    open_interest: int
    implied_volatility: float | None = None


@dataclass(frozen=True)
class ScreenContext:
    """Run-wide facts. `macro_*` come from v7's state/macro-latest.json;
    `option_level` is get_accounts' string for v7's configured account
    (e.g. "option_level_2")."""

    quotes_live: bool
    macro_restricted: bool | None
    macro_hard_gate_active: bool | None
    option_level: str | None = None
    leverage_mode: bool = False


def _spread_check(bid: float, ask: float, max_pct: float) -> GateCheck:
    if bid <= 0 or ask <= 0 or ask < bid:
        return GateCheck("quoted_spread", False, f"invalid quote bid={bid} ask={ask}")
    pct = (ask - bid) / ((ask + bid) / 2) * 100
    return GateCheck("quoted_spread", pct <= max_pct, f"{pct:.2f}% (max {max_pct}%)")


def _oi_check(oi: int, minimum: int) -> GateCheck:
    return GateCheck("open_interest", oi >= minimum, f"{oi} (min {minimum})")


def _liquidity(spread: GateCheck, oi: GateCheck, quotes_live: bool) -> tuple[list[GateCheck], list[str]]:
    """Closing and after-hours spreads over-reject (the project's 2026-07-08
    run 1). With the market closed, a wide spread becomes a warning to
    re-check at the open, not a veto. Open interest is an end-of-day number
    and stays a gate either way."""
    if quotes_live or spread.passed:
        return [spread, oi], []
    return [oi], [f"spread {spread.reason} on a closed-market quote: provisional, re-check at the open"]


def _range_check(name: str, value: float, lo: float, hi: float) -> GateCheck:
    return GateCheck(name, lo <= value <= hi, f"{value:g} (need {lo:g}-{hi:g})")


def _no_contract() -> tuple[list[GateCheck], list[str], None]:
    return [GateCheck("contract", False, "no contract priced")], [], None


def shares_gates(cfg: dict, market: MarketInputs):
    warn_days = get(cfg, "vehicles.shares.earnings_warning_days")
    warnings = []
    if market.days_to_earnings is not None and market.days_to_earnings <= warn_days:
        warnings.append(f"earnings in {market.days_to_earnings}d: a binary event lands right after entry")
    return [], warnings, None


def short_call_gates(cfg: dict, c: ContractQuote | None, ctx: ScreenContext):
    if c is None:
        return _no_contract()
    sc = get(cfg, "vehicles.short_call")
    lo, hi = sc["delta_range"]
    label = None
    if ctx.leverage_mode:
        lo = sc["leverage_delta_min"]
        if c.delta < sc["delta_range"][0]:
            label = "LEVERAGE"
    checks = [_range_check("dte", c.dte_days, *sc["dte_range"]), _range_check("delta", c.delta, lo, hi)]
    liq, warnings = _liquidity(
        _spread_check(c.bid, c.ask, sc["quoted_spread_max_pct"]),
        _oi_check(c.open_interest, sc["open_interest_min"]), ctx.quotes_live,
    )
    return checks + liq, warnings, label


def csp_gates(cfg: dict, c: ContractQuote | None, ctx: ScreenContext, market: MarketInputs):
    if c is None:
        return _no_contract()
    cc = get(cfg, "vehicles.csp")
    if not ctx.option_level:
        permitted = GateCheck("options_level", False, "account options level not confirmed")
    else:
        ok = ctx.option_level in cc["permitted_option_levels"]
        permitted = GateCheck("options_level", ok,
                              f"{ctx.option_level} {'permits' if ok else 'excludes'} cash-secured puts")
    checks = [
        permitted,
        _range_check("dte", c.dte_days, *cc["dte_range"]),
        _range_check("put_delta", c.delta, *cc["put_delta_range"]),
    ]
    liq, warnings = _liquidity(
        _spread_check(c.bid, c.ask, cc["quoted_spread_max_pct"]),
        _oi_check(c.open_interest, cc["open_interest_min"]), ctx.quotes_live,
    )
    if market.days_to_earnings is not None and market.days_to_earnings <= c.dte_days:
        warnings.append(f"earnings in {market.days_to_earnings}d fall inside the expiry: assignment on a gap is possible")
    return checks + liq, warnings, None


def leap_gates(v7cfg: dict, c: ContractQuote | None, ctx: ScreenContext, market: MarketInputs,
               catalyst_horizon_days: int | None):
    if c is None:
        return _no_contract()
    checks = []
    macro_known = ctx.macro_restricted is not None and ctx.macro_hard_gate_active is not None
    if not macro_known:
        checks.append(GateCheck("macro_state", False, "v7 macro state unavailable"))
    # Unknown macro reads as restricted with no hard gate, so the delta
    # check still says whether the contract would clear the stricter band.
    delta = evaluate_delta_policy(
        v7cfg, c.delta,
        hard_gate_active=bool(ctx.macro_hard_gate_active),
        restricted=ctx.macro_restricted is not False,
    )
    checks.append(GateCheck("delta_policy", delta.permitted, delta.reason))
    checks.append(dte_gate(c.dte_days, v7cfg))
    checks.append(catalyst_duration_gate(catalyst_horizon_days, c.dte_days))
    liq, warnings = _liquidity(
        spread_gate(c.bid, c.ask, v7cfg), open_interest_gate(c.open_interest, v7cfg), ctx.quotes_live,
    )
    blackout = get(v7cfg, "event_gates.binary_event_blackout_days")
    if market.days_to_earnings is not None and market.days_to_earnings <= blackout:
        warnings.append(f"earnings in {market.days_to_earnings}d: v7 §7 would block entry until after the print")
    return checks + liq, warnings, "UNSIZED"


def short_call_penalties(cfg: dict, market: MarketInputs, vol_score: float | None, dte: int,
                         has_earnings: bool = True, contract_iv: float | None = None):
    """(floor penalty, ceiling penalty, notes). An unknown input costs the
    floor but not the ceiling, the same bounding the factors use. ETFs
    report no earnings, so for them a missing date means none, not unknown.

    IV crush is about the contract actually being bought: an expiry that
    spans earnings carries the event premium, which the 30-day ATM IV behind
    `vol_score` may not (PLTR, 2026-09-21: 58% on the Nov call vs 47.5%
    ATM). So when the contract's IV and HV30 are both known, "expensive" is
    judged from them."""
    if contract_iv is not None and market.hv30:
        vol_score = volatility_pricing_score(cfg, MarketInputs(atm_iv=contract_iv, hv30=market.hv30))
    sc = get(cfg, "vehicles.short_call")
    expensive_at = get(cfg, "factors.volatility_pricing.expensive_at_or_below_score")
    floor_pen = ceil_pen = 0.0
    notes = []

    crush = sc["iv_crush_penalty"]
    if market.days_to_earnings is not None:
        earnings_inside = market.days_to_earnings <= dte
    else:
        earnings_inside = None if has_earnings else False
    expensive = None if vol_score is None else vol_score <= expensive_at
    if earnings_inside is not False and expensive is not False:
        floor_pen += crush
        if earnings_inside and expensive:
            ceil_pen += crush
            notes.append(f"IV crush: earnings in {market.days_to_earnings}d inside a {dte}d expiry with the contract's "
                         f"IV expensive, {vol_score:.1f}/10 (-{crush})")
        else:
            notes.append(f"IV crush unverified (earnings date or IV level unknown): floor -{crush}")

    no_cat = sc["no_catalyst_penalty"]
    catalyst_inside = None if market.days_to_nearest_catalyst is None else market.days_to_nearest_catalyst <= dte
    if catalyst_inside is not True:
        floor_pen += no_cat
        if catalyst_inside is False:
            ceil_pen += no_cat
            notes.append(f"nearest catalyst {market.days_to_nearest_catalyst}d out, past the {dte}d expiry (-{no_cat})")
        else:
            notes.append(f"no dated catalyst identified: floor -{no_cat}")
    return floor_pen, ceil_pen, notes


# ------------------------------------------------------------- screen -----

@dataclass(frozen=True)
class ScreenInputs:
    ticker: str
    name: NameInputs
    judged: JudgedFactors
    market: MarketInputs
    catalyst_horizon_days: int | None = None
    short_call: ContractQuote | None = None
    csp: ContractQuote | None = None
    leap: ContractQuote | None = None


@dataclass(frozen=True)
class VehicleResult:
    vehicle: str
    eligible: bool
    gates: list[GateCheck]
    warnings: list[str]
    score_floor: int
    score_ceiling: int
    confidence: str
    label: str | None = None
    contract: ContractQuote | None = None


@dataclass(frozen=True)
class ScreenResult:
    ticker: str
    instrument_type: str
    disqualified: bool
    name_gates: list[GateCheck]
    vehicles: dict[str, VehicleResult]
    best_vehicle: str | None
    composite: int | None
    composite_ceiling: int | None
    confidence: str | None
    verdict: str  # "BEST FIT", "PASS", "INCOMPLETE" or "DISQUALIFIED"
    verdict_reason: str
    factor_bounds: FactorBounds | None = None


def _confidence(cfg: dict, gap: int, option_vehicle: bool, quotes_live: bool) -> str:
    level = "High" if gap <= get(cfg, "confidence.high_max_gap") else (
        "Med" if gap <= get(cfg, "confidence.med_max_gap") else "Low")
    if option_vehicle and not quotes_live and level == "High":
        level = "Med"
    return level


def screen(cfg: dict, v7cfg: dict, inputs: ScreenInputs, ctx: ScreenContext) -> ScreenResult:
    name_gates = name_disqualifiers(cfg, inputs.name)
    failed = [g for g in name_gates if not g.passed]
    if failed:
        return ScreenResult(
            ticker=inputs.ticker, instrument_type=inputs.name.instrument_type, disqualified=True,
            name_gates=name_gates, vehicles={}, best_vehicle=None, composite=None,
            composite_ceiling=None, confidence=None, verdict="DISQUALIFIED",
            verdict_reason="; ".join(f"{g.name}: {g.reason}" for g in failed),
        )

    bounds = factor_bounds(cfg, inputs.judged, inputs.market)
    vol = volatility_pricing_score(cfg, inputs.market)
    gate_fns = {
        "shares": lambda: shares_gates(cfg, inputs.market),
        "short_call": lambda: short_call_gates(cfg, inputs.short_call, ctx),
        "csp": lambda: csp_gates(cfg, inputs.csp, ctx, inputs.market),
        "leap": lambda: leap_gates(v7cfg, inputs.leap, ctx, inputs.market, inputs.catalyst_horizon_days),
    }
    vehicles: dict[str, VehicleResult] = {}
    for v in VEHICLES:
        checks, warnings, label = gate_fns[v]()
        floor = _weighted(cfg, v, bounds.floor)
        ceiling = _weighted(cfg, v, bounds.ceiling)
        if v == "short_call":
            dte = inputs.short_call.dte_days if inputs.short_call else get(cfg, "vehicles.short_call.dte_range")[1]
            fp, cp, notes = short_call_penalties(
                cfg, inputs.market, vol, dte,
                has_earnings=inputs.name.instrument_type == "stock",
                contract_iv=inputs.short_call.implied_volatility if inputs.short_call else None)
            floor, ceiling = floor - fp, ceiling - cp
            warnings = warnings + notes
        lo = _round_half_up(_clamp(floor, 0, 100))
        hi = _round_half_up(_clamp(ceiling, 0, 100))
        vehicles[v] = VehicleResult(
            vehicle=v, eligible=all(c.passed for c in checks), gates=checks, warnings=warnings,
            score_floor=lo, score_ceiling=hi,
            confidence=_confidence(cfg, hi - lo, v in OPTION_VEHICLES, ctx.quotes_live),
            label=label, contract=getattr(inputs, v) if v in OPTION_VEHICLES else None,
        )

    # Shares carry no vehicle-level gates, so a name that clears the
    # disqualifiers always has at least one eligible vehicle.
    order = get(cfg, "verdict.tie_break_order")
    eligible = [r for r in vehicles.values() if r.eligible]
    pass_below = get(cfg, "verdict.pass_below")
    best = min(eligible, key=lambda r: (-r.score_floor, order.index(r.vehicle)))
    # A PASS has to hold whatever the missing inputs turn out to be. If any
    # eligible vehicle's ceiling reaches the pass line, the data gaps decide
    # the verdict, and saying PASS would be a guess (CEG replay, 2026-09-21).
    open_ended = [r for r in eligible if r.score_ceiling >= pass_below]
    if best.score_floor >= pass_below:
        verdict, reason = "BEST FIT", f"{best.vehicle} scores {best.score_floor} (pass line {pass_below})"
    elif open_ended:
        top = max(open_ended, key=lambda r: r.score_ceiling)
        verdict, reason = "INCOMPLETE", (
            f"missing inputs could lift {top.vehicle} from {top.score_floor} to {top.score_ceiling}, "
            f"across the pass line {pass_below}")
    else:
        verdict, reason = "PASS", f"best vehicle scores {best.score_floor}, below {pass_below}"
    return ScreenResult(
        ticker=inputs.ticker, instrument_type=inputs.name.instrument_type, disqualified=False,
        name_gates=name_gates, vehicles=vehicles, best_vehicle=best.vehicle,
        composite=best.score_floor, composite_ceiling=best.score_ceiling,
        confidence=best.confidence, verdict=verdict, verdict_reason=reason, factor_bounds=bounds,
    )


_CONFIDENCE_ORDER = {"High": 0, "Med": 1, "Low": 2, None: 3}


def rank(results: list[ScreenResult]) -> list[ScreenResult]:
    """Scored names first by composite (floor), then confidence, then
    ticker; unscorable names after them, disqualified names last."""
    return sorted(results, key=lambda r: (
        r.disqualified, r.composite is None, -(r.composite or 0),
        _CONFIDENCE_ORDER[r.confidence], r.ticker,
    ))


# ------------------------------------------------ deep dive: scenarios ----

@dataclass(frozen=True)
class PriceScenario:
    label: str
    probability: float
    price: float  # the underlying at the vehicle's horizon


def check_scenarios(scenarios: list[PriceScenario]) -> None:
    if not scenarios:
        raise ValueError("no scenarios")
    if any(s.probability < 0 for s in scenarios):
        raise ValueError("negative scenario probability")
    total = sum(s.probability for s in scenarios)
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"scenario probabilities sum to {total:.4f}, not 1")


def shares_returns(spot: float, scenarios: list[PriceScenario]) -> list[float]:
    return [(s.price - spot) / spot for s in scenarios]


def call_returns(entry_premium: float, strike: float, scenarios: list[PriceScenario],
                 tau_remaining_years: float, r: float, q: float, sigma_exit: float) -> list[float]:
    """Each scenario's price reprices the call at the horizon, with
    `tau_remaining_years` left on it (0 = held to expiry, intrinsic only)."""
    return [
        (bs_call_price(s.price, strike, tau_remaining_years, r, q, sigma_exit) - entry_premium) / entry_premium
        for s in scenarios
    ]


def csp_returns(premium: float, strike: float, scenarios: list[PriceScenario]) -> list[float]:
    """Return on the cash securing the put, held to expiry:
    (premium - max(0, K - S_T)) / K. Assignment is marked to market at the
    scenario price, not treated as a free entry."""
    return [(premium - max(0.0, strike - s.price)) / strike for s in scenarios]


def executable_sale(bid: float, ask: float, fees: float, v7cfg: dict) -> float:
    """What selling a put actually collects: the bid less the same slippage
    fraction v7 §12.2 charges on entry, less fees. Never the midpoint."""
    slip = get(v7cfg, "pricing.entry_slippage_fraction_of_spread")
    return bid - slip * (ask - bid) - fees


def regime_kelly_multiplier(v7cfg: dict, restricted: bool | None) -> float:
    """v7's regime throttle, reused. An unknown regime reads restricted."""
    key = "kelly_multiplier_normal" if restricted is False else "kelly_multiplier_restricted"
    return get(v7cfg, f"restricted_regime.{key}")


@dataclass(frozen=True)
class GrowthSummary:
    ev: float
    expected_loss: float
    ev_to_el: float | None
    position_geometric_return: float  # exp(E[log(1+R)]) - 1; -1.0 if any live scenario is a total loss
    kelly_f_star: float
    kelly_multiplier: float
    fraction: float                   # kelly_multiplier * kelly_f_star, of NAV
    egr: float                        # E[log(1 + fraction * R)]: NAV growth per trade at that fraction


def growth_summary(probs: list[float], rets: list[float], kelly_multiplier: float,
                   f_cap: float = 1.0) -> GrowthSummary:
    """The chat-era "Expected Geometric Return", made comparable across
    vehicles. At full size a long option with a total-loss scenario always
    has a -100% geometric return, which says nothing, so the comparable
    figure is `egr`: expected log growth of NAV at the regime-throttled
    Kelly fraction."""
    ev = sum(p * r for p, r in zip(probs, rets))
    el = sum(p * max(0.0, -r) for p, r in zip(probs, rets))
    if any(p > 0 and r <= -1.0 for p, r in zip(probs, rets)):
        pgr = -1.0
    else:
        pgr = math.exp(sum(p * math.log(1 + r) for p, r in zip(probs, rets))) - 1
    f_star = kelly_f_star(probs, rets, f_cap)
    fraction = kelly_multiplier * f_star
    return GrowthSummary(
        ev=ev, expected_loss=el, ev_to_el=ev / el if el > 0 else None,
        position_geometric_return=pgr, kelly_f_star=f_star, kelly_multiplier=kelly_multiplier,
        fraction=fraction, egr=_kelly_growth(fraction, probs, rets),
    )


@dataclass(frozen=True)
class SizeResult:
    vehicle: str
    fraction_of_nav: float     # capital committed: share value, call premium, or put collateral
    binding: str               # "kelly", "max_loss_cap" or "no_edge"
    max_loss_fraction: float   # of committed capital, in the worst case
    units: int | None          # shares or contracts; None when NAV wasn't supplied
    min_nav_for_one_unit: float  # ADR 0013's min_feasible_nav, for this vehicle


def size_position(cfg: dict, vehicle: str, growth: GrowthSummary, rets: list[float],
                  unit_cost: float, nav: float | None = None) -> SizeResult:
    """min(throttled Kelly, the max-loss cap). A long call's worst case is
    the whole premium whatever the scenarios say; shares and puts use the
    worst scenario. `unit_cost` is per share, or per contract (premium x 100,
    or strike x 100 of collateral for a put)."""
    if vehicle == "leap":
        raise ValueError("LEAP sizing belongs to v7: run bench-check or daily-screen")
    if vehicle not in ("shares", "short_call", "csp"):
        raise ValueError(f"unknown vehicle {vehicle!r}")
    loss = 1.0 if vehicle == "short_call" else max(0.0, -min(rets))
    if growth.kelly_f_star <= 0:
        return SizeResult(vehicle, 0.0, "no_edge", loss, 0 if nav else None, math.inf)
    cap = get(cfg, f"sizing.max_loss_pct_nav.{vehicle}") / 100.0
    f_cap = cap / loss if loss > 0 else math.inf
    f, binding = (growth.fraction, "kelly") if growth.fraction <= f_cap else (f_cap, "max_loss_cap")
    units = math.floor(f * nav / unit_cost) if nav else None
    return SizeResult(vehicle, f, binding, loss, units, unit_cost / f if f > 0 else math.inf)


# ----------------------------------------------------- strike for delta --

def _norm_ppf(p: float) -> float:
    """Inverse standard normal CDF by bisection on math.erf; no scipy (ADR 0010)."""
    lo, hi = -10.0, 10.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if 0.5 * (1 + math.erf(mid / math.sqrt(2))) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def strike_for_delta(spot: float, delta: float, dte_days: int, iv: float, rate: float = 0.04,
                     dividend_yield: float = 0.0, put: bool = False) -> float:
    """The Black-Scholes strike with the given absolute delta: where to aim
    the first quote batch. A 0.25-delta put sits at the same strike as a
    0.75-delta call. The quoted delta is still what counts; this only saves
    lookup rounds (the rough `0.5·σ·√T` rule missed LEAPs by 10+ points of
    moneyness at high IV on 2026-09-21)."""
    if not 0 < delta < 1:
        raise ValueError(f"delta {delta} must be between 0 and 1")
    call_delta = 1 - delta if put else delta
    t = dte_days / 365.0
    d1 = _norm_ppf(call_delta / math.exp(-dividend_yield * t))
    return spot * math.exp(-d1 * iv * math.sqrt(t) + (rate - dividend_yield + 0.5 * iv * iv) * t)


# -------------------------------------------------- technicals from data --

def technicals(closes: list[float], *, last_close: float | None = None, rsi14: float | None = None,
               sma50: float | None = None, sma200: float | None = None, high_52w: float | None = None,
               avg_volume: float | None = None, volumes: list[float] | None = None,
               hv_trim_largest: int = 0) -> dict:
    """The screen's mechanical market inputs, from whatever the skill could
    fetch cheaply. `closes` (oldest first) needs 31+ values for hv30; the
    indicator values Robinhood computes over a full year (RSI14, SMA50,
    SMA200) and the fundamentals' 52-week high and average volume can be
    passed in rather than derived. A value is only derived from `closes`
    when the series is long enough for it to be right: RSI from 31 closes
    would be a different number from RSI over a year. Anything unavailable
    comes back None, and the screen bounds it. `market.hv30` drops the
    `hv_trim_largest` biggest moves (config); the untrimmed figure is kept
    under `for_judgment`."""
    last = last_close if last_close is not None else (closes[-1] if closes else None)
    n = len(closes)
    if rsi14 is None and n >= 100:
        rsi14 = rsi_wilder(closes, 14)
    if sma50 is None and n >= 50:
        sma50 = sma(closes, 50)
    if sma200 is None and n >= 200:
        sma200 = sma(closes, 200)
    if high_52w is None and n >= 252:
        high_52w = rolling_max(closes, 252)

    def pct(ref):
        return (last / ref - 1) * 100 if last is not None and ref else None

    if avg_volume is not None and last is not None:
        adv = avg_volume * last
    elif volumes and n:
        k = min(20, n, len(volumes))
        adv = statistics.fmean(c * v for c, v in zip(closes[-k:], volumes[-k:]))
    else:
        adv = None
    # Shaped like the input file, so each block pastes straight in and
    # nothing lands in the wrong one.
    enough = n > 30
    return {
        "market": {"rsi14": rsi14, "pct_above_50dma": pct(sma50),
                   "hv30": realized_vol(closes, 30, trim_largest=hv_trim_largest) if enough else None},
        "name": {"avg_daily_dollar_volume": adv},
        "for_judgment": {"last_close": last, "pct_vs_200dma": pct(sma200),
                         "pct_from_52w_high": pct(high_52w),
                         "hv30_untrimmed": realized_vol(closes, 30) if enough else None},
    }


def _bars_from_payload(payload) -> tuple[list[float], list[float]]:
    """A saved `get_equity_historicals` payload for one symbol, or a bare
    list of closes. Interpolated bars are dropped, as in
    engine.sources.parse_robinhood_daily_closes."""
    if isinstance(payload, list):
        return [float(x) for x in payload], []
    results = (payload.get("data") or payload).get("results") or []
    if len(results) != 1:
        raise ValueError(f"expected one symbol's bars, got {len(results)}")
    bars = sorted(
        (b for b in results[0].get("bars") or []
         if not b.get("interpolated") and b.get("close_price") not in (None, "")),
        key=lambda b: b["begins_at"],
    )
    return [float(b["close_price"]) for b in bars], [float(b.get("volume") or 0) for b in bars]


# --------------------------------------------------------------- CLI ------

def _macro_context(macro_path: str | None, v7cfg: dict, today: str) -> dict:
    """Reads v7's cached macro state; never recomputes it (bench-check's
    rule). Missing file -> unknown, which the LEAP row fails closed on."""
    if not macro_path or not Path(macro_path).exists():
        return {"restricted": None, "hard_gate_active": None, "banner": "MACRO STATE UNAVAILABLE"}
    m = json.loads(Path(macro_path).read_text())
    restricted = (m.get("restricted_regime") or {}).get("restricted")
    gates = m.get("hard_gates") or {}
    active = [k for k, g in gates.items() if g.get("active")]
    last = m.get("last_refreshed") or m.get("as_of")
    stale = macro_staleness(last, today, v7cfg) if last else None
    rr = m.get("restricted_regime") or {}
    return {
        "restricted": restricted if isinstance(restricted, bool) else None,
        "hard_gate_active": bool(active) if gates else None,
        "active_hard_gates": active,
        "R": rr.get("R"),
        "last_refreshed": last,
        "staleness_band": stale.band if stale else None,
        "banner": None if stale and stale.band == "current" else
                  f"STALE MACRO CONTEXT (last refreshed {last})",
    }


def _watchlist_status(watchlist_path: str | None) -> dict[str, str]:
    if not watchlist_path or not Path(watchlist_path).exists():
        return {}
    w = json.loads(Path(watchlist_path).read_text())
    return {n["ticker"]: n.get("status", "unknown") for n in w.get("names", [])}


def _contract(d: dict | None) -> ContractQuote | None:
    return ContractQuote(**d) if d else None


_TOP_KEYS = {"ticker", "instrument_type", "context", "name", "judged", "market",
             "catalyst_horizon_days", "contracts", "deep_dive"}
_CONTEXT_KEYS = {"quotes_live", "option_level", "leverage_mode"}


def inputs_from_json(d: dict) -> tuple[ScreenInputs, dict]:
    """One ticker's input file -> (ScreenInputs, its context block). Unknown
    keys raise at every level: a misspelled field would otherwise read as
    missing and quietly lower the score."""
    for where, keys, allowed in (("file", d, _TOP_KEYS), ("context", d.get("context") or {}, _CONTEXT_KEYS),
                                 ("contracts", d.get("contracts") or {}, set(OPTION_VEHICLES))):
        unknown = set(keys) - allowed
        if unknown:
            raise ValueError(f"unknown {where} key(s): {sorted(unknown)}")
    contracts = d.get("contracts") or {}
    inputs = ScreenInputs(
        ticker=d["ticker"],
        name=NameInputs(instrument_type=d["instrument_type"], **(d.get("name") or {})),
        judged=JudgedFactors(**{k: v["score"] if isinstance(v, dict) else v
                                for k, v in (d.get("judged") or {}).items()}),
        market=MarketInputs(**(d.get("market") or {})),
        catalyst_horizon_days=d.get("catalyst_horizon_days"),
        short_call=_contract(contracts.get("short_call")),
        csp=_contract(contracts.get("csp")),
        leap=_contract(contracts.get("leap")),
    )
    return inputs, d.get("context") or {}


def _jsonable(obj):
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


def _context_for(file_ctx: dict, macro: dict) -> ScreenContext:
    return ScreenContext(
        quotes_live=bool(file_ctx.get("quotes_live", False)),
        macro_restricted=macro["restricted"],
        macro_hard_gate_active=macro["hard_gate_active"],
        option_level=file_ctx.get("option_level"),
        leverage_mode=bool(file_ctx.get("leverage_mode", False)),
    )


def _leap_label(ticker: str, status: dict[str, str]) -> str:
    if ticker in status:
        return f"ON v7 WATCHLIST ({status[ticker]}): run bench-check for the v7 verdict and size"
    return "OUTSIDE v7, UNSIZED: propose for Stage A if it holds up"


def _cmd_screen(args) -> dict:
    cfg = load_screen_config(args.config)
    v7cfg = load_config(args.v7_config)
    macro = _macro_context(args.macro, v7cfg, args.today)
    status = _watchlist_status(args.watchlist)
    results = []
    for path in args.inputs:
        inputs, file_ctx = inputs_from_json(json.loads(Path(path).read_text()))
        results.append(screen(cfg, v7cfg, inputs, _context_for(file_ctx, macro)))
    ranked = rank(results)
    out = []
    for r in ranked:
        d = _jsonable(r)
        if "leap" in r.vehicles:
            d["vehicles"]["leap"]["label"] = _leap_label(r.ticker, status)
        out.append(d)
    return {"macro": macro, "ranked": out}


def _cmd_deep_dive(args) -> dict:
    """Per-vehicle scenario math for one ticker's input file, whose
    `deep_dive` block carries spot, rate, optional NAV, and bull/base/bear
    price scenarios per vehicle horizon."""
    cfg = load_screen_config(args.config)
    v7cfg = load_config(args.v7_config)
    macro = _macro_context(args.macro, v7cfg, args.today)
    d = json.loads(Path(args.input).read_text())
    inputs, _ = inputs_from_json(d)
    dd = d["deep_dive"]
    spot, r, q = dd["spot"], dd.get("rate", 0.04), dd.get("dividend_yield", 0.0)
    nav = dd.get("nav")
    fees = dd.get("fees_per_share", 0.0)
    mult = regime_kelly_multiplier(v7cfg, macro["restricted"])
    out = {"kelly_multiplier": mult, "vehicles": {}}
    for v, raw in (dd.get("scenarios") or {}).items():
        scenarios = [PriceScenario(**s) for s in raw]
        check_scenarios(scenarios)
        probs = [s.probability for s in scenarios]
        c = getattr(inputs, v, None) if v in OPTION_VEHICLES else None
        if v in OPTION_VEHICLES and c is None:
            out["vehicles"][v] = {"error": "no contract in the input file"}
            continue
        if v == "shares":
            rets, unit_cost, entry = shares_returns(spot, scenarios), spot, spot
        elif v in ("short_call", "leap"):
            entry = executable_entry(c.ask, c.bid, fees, v7cfg)
            horizon_days = dd.get("horizon_days", {}).get(v, c.dte_days)
            tau = max(0.0, (c.dte_days - horizon_days) / 365.0)
            sigma = dd.get("exit_iv", {}).get(v, c.implied_volatility)
            if sigma is None:
                out["vehicles"][v] = {"error": "no exit IV: pass deep_dive.exit_iv or the contract's implied_volatility"}
                continue
            rets, unit_cost = call_returns(entry, c.strike, scenarios, tau, r, q, sigma), entry * 100
        elif v == "csp":
            entry = executable_sale(c.bid, c.ask, fees, v7cfg)
            rets, unit_cost = csp_returns(entry, c.strike, scenarios), c.strike * 100
        else:
            raise ValueError(f"unknown vehicle {v!r}")
        g = growth_summary(probs, rets, mult)
        row = {"entry": entry, "returns": {s.label: ret for s, ret in zip(scenarios, rets)},
               "growth": _jsonable(g)}
        if v == "leap":
            row["size"] = "UNSIZED: v7 owns LEAP sizing (bench-check / daily-screen)"
        else:
            row["size"] = _jsonable(size_position(cfg, v, g, rets, unit_cost, nav))
        out["vehicles"][v] = row
    return out


def _cmd_strike(args) -> dict:
    k = strike_for_delta(args.spot, args.delta, args.dte, args.iv, args.rate, args.dividend_yield, args.put)
    return {"strike": round(k, 2), "delta": args.delta, "type": "put" if args.put else "call", "dte_days": args.dte}


def _cmd_technicals(args) -> dict:
    """Input: a saved `get_equity_historicals` payload for one symbol, a bare
    list of closes, or an object {"closes": [...], "last_close", "rsi14",
    "sma50", "sma200", "high_52w", "avg_volume"} with any of those keys."""
    trim = get(load_screen_config(args.config), "factors.volatility_pricing.hv_trim_largest_moves")
    payload = json.loads(Path(args.input).read_text())
    if isinstance(payload, dict) and "closes" in payload:
        extras = {k: payload.get(k) for k in
                  ("last_close", "rsi14", "sma50", "sma200", "high_52w", "avg_volume")}
        return technicals([float(c) for c in payload["closes"]], hv_trim_largest=trim, **extras)
    closes, volumes = _bars_from_payload(payload)
    return technicals(closes, volumes=volumes or None, hv_trim_largest=trim)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python3 -m engine.vehicle")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("technicals", help="RSI14, %% above 50DMA, HV30 and context from closes and indicator values")
    t.add_argument("input")
    t.add_argument("--config", default=str(CONFIG_PATH))

    k = sub.add_parser("strike", help="Black-Scholes strike for a target delta, to aim the first quote batch")
    k.add_argument("--spot", type=float, required=True)
    k.add_argument("--delta", type=float, required=True, help="absolute delta, e.g. 0.70 (or 0.25 with --put)")
    k.add_argument("--dte", type=int, required=True)
    k.add_argument("--iv", type=float, required=True, help="as a fraction, e.g. 0.45")
    k.add_argument("--rate", type=float, default=0.04)
    k.add_argument("--dividend-yield", type=float, default=0.0)
    k.add_argument("--put", action="store_true")

    for name in ("screen", "deep-dive"):
        s = sub.add_parser(name)
        s.add_argument("--config", default=str(CONFIG_PATH))
        s.add_argument("--v7-config", required=True)
        s.add_argument("--macro")
        s.add_argument("--today", default=date.today().isoformat())
        if name == "screen":
            s.add_argument("--watchlist")
            s.add_argument("inputs", nargs="+")
        else:
            s.add_argument("input")

    args = p.parse_args(argv)
    handler = {"technicals": _cmd_technicals, "strike": _cmd_strike, "screen": _cmd_screen,
               "deep-dive": _cmd_deep_dive}[args.cmd]
    json.dump(handler(args), sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
