"""§15's joint portfolio variance/expected-shortfall test and the
ITM-to-ATM roll math. Reprices every position under correlated scenarios
via `engine.optmodel.bs_call_price` rather than a separate pricing path, so
a position never gets marked differently here than it would on entry.

No numpy (ADR 0010): Cholesky decomposition and the risk statistics below
are all plain nested-loop/stdlib Python, adequate at the position counts a
15-25 name watchlist implies.
"""
from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass

from .optmodel import bs_call_price


# --------------------------------------------------- correlated scenarios --

def cholesky(cov: list[list[float]]) -> list[list[float]]:
    """Lower-triangular L such that cov = L @ L^T, for a symmetric
    positive-semi-definite covariance matrix."""
    n = len(cov)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                L[i][j] = math.sqrt(max(cov[i][i] - s, 0.0))
            else:
                L[i][j] = (cov[i][j] - s) / L[j][j] if L[j][j] != 0 else 0.0
    return L


def correlated_normal_draws(
    cov: list[list[float]], n_draws: int, seed: int | None = None
) -> list[list[float]]:
    """`n_draws` samples of a zero-mean multivariate normal with covariance
    `cov`, via Cholesky (z ~ N(0,I); x = L @ z). Row/column order of `cov`
    must match the order of the positions it will shock."""
    L = cholesky(cov)
    n = len(cov)
    rng = random.Random(seed)
    draws = []
    for _ in range(n_draws):
        z = [rng.gauss(0.0, 1.0) for _ in range(n)]
        draws.append([sum(L[i][k] * z[k] for k in range(n)) for i in range(n)])
    return draws


# -------------------------------------------------------- position pricing --

@dataclass(frozen=True)
class Position:
    label: str
    contracts: int
    strike: float
    spot: float
    tau_years: float
    r: float
    q: float
    sigma: float
    entry_cost_per_contract: float  # dollars, ×100 multiplier already applied


def reprice_position(pos: Position, spot_return: float, tau_elapsed_years: float, sigma_shift: float) -> float:
    new_spot = pos.spot * (1 + spot_return)
    new_tau = max(0.0, pos.tau_years - tau_elapsed_years)
    new_sigma = max(0.01, pos.sigma + sigma_shift)
    price_per_share = bs_call_price(new_spot, pos.strike, new_tau, pos.r, pos.q, new_sigma)
    return pos.contracts * 100 * price_per_share


def position_pnl(pos: Position, spot_return: float, tau_elapsed_years: float, sigma_shift: float) -> float:
    return reprice_position(pos, spot_return, tau_elapsed_years, sigma_shift) - pos.contracts * pos.entry_cost_per_contract


def portfolio_pnl(
    positions: list[Position], spot_returns: list[float], tau_elapsed_years: float, sigma_shift: float
) -> float:
    """`spot_returns` aligns 1:1 with `positions`, in the same order used to
    build the covariance matrix they were drawn from."""
    return sum(position_pnl(p, r, tau_elapsed_years, sigma_shift) for p, r in zip(positions, spot_returns))


def simulate_portfolio_pnl_distribution(
    positions: list[Position], cov: list[list[float]], n_draws: int,
    tau_elapsed_years: float, sigma_shift_std: float = 0.05, seed: int | None = None,
) -> list[float]:
    """§15's 21-trading-day-horizon P&L distribution via correlated
    log-normal spot shocks and one common vol-regime shock per draw
    (a simplification: real vol-surface moves differ by name; a single
    shared shock is the tractable stdlib-only first cut).
    `cov` should be the covariance of log returns scaled to the horizon —
    build it from the same daily-return history `engine.priceseries.daily_returns`
    already produces elsewhere in the engine."""
    draws = correlated_normal_draws(cov, n_draws, seed=seed)
    rng = random.Random(seed)
    pnls = []
    for z in draws:
        spot_returns = [math.exp(x) - 1 for x in z]
        sigma_shift = rng.gauss(0.0, sigma_shift_std)
        pnls.append(portfolio_pnl(positions, spot_returns, tau_elapsed_years, sigma_shift))
    return pnls


# ----------------------------------------------------------- risk statistics

def value_at_risk(pnls: list[float], confidence: float = 0.95) -> float:
    """A positive loss number: the `confidence`-quantile of the loss
    distribution (95% VaR is exceeded only 5% of the time)."""
    losses = sorted(-p for p in pnls)
    idx = max(0, min(len(losses) - 1, int(confidence * len(losses))))
    return losses[idx]


def expected_shortfall(pnls: list[float], confidence: float = 0.95) -> float:
    """ES_95%: the average loss in the worst (1-confidence) tail."""
    losses = sorted(-p for p in pnls)
    cutoff = max(1, int((1 - confidence) * len(losses)))
    return statistics.fmean(losses[-cutoff:])


@dataclass(frozen=True)
class PortfolioRiskResult:
    variance_old: float
    variance_new: float
    es95_old: float
    es95_new: float
    passes_variance: bool
    passes_es95: bool

    @property
    def passes(self) -> bool:
        return self.passes_variance and self.passes_es95


def evaluate_portfolio_risk(pnls_old: list[float], pnls_new: list[float]) -> PortfolioRiskResult:
    """§15 requires BOTH Var(Π_new)<=Var(Π_old) and ES_95%(Π_new)<=ES_95%(Π_old)
    — unconditionally; §20's require_variance_non_increasing /
    require_es95_non_increasing flags document that both are on, not a
    toggle this function reads."""
    var_old, var_new = statistics.variance(pnls_old), statistics.variance(pnls_new)
    es_old, es_new = expected_shortfall(pnls_old), expected_shortfall(pnls_new)
    return PortfolioRiskResult(
        variance_old=var_old, variance_new=var_new, es95_old=es_old, es95_new=es_new,
        passes_variance=var_new <= var_old, passes_es95=es_new <= es_old,
    )


# -------------------------------------------------------- ITM-to-ATM rolls --

def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _matvec(M: list[list[float]], v: list[float]) -> list[float]:
    return [_dot(row, v) for row in M]


def _quad_form(v: list[float], M: list[list[float]]) -> float:
    return _dot(v, _matvec(M, v))


def exposure_vector(contracts: int, spot: float, delta: float, vega: float, gamma: float) -> list[float]:
    """g_i = (100*S*Delta, 100*Vega, 50*S^2*Gamma) per §15's roll math,
    scaled by contract count."""
    return [contracts * 100 * spot * delta, contracts * 100 * vega, contracts * 50 * spot**2 * gamma]


@dataclass(frozen=True)
class RollResult:
    n_a_max: int
    discriminant: float
    permitted: bool
    reason: str


def evaluate_itm_to_atm_roll(
    g0: list[float], g_old_per_contract: list[float], g_new_per_contract: list[float],
    sigma: list[list[float]], n_old_contracts: int,
    es_rises: bool | None = None, any_sizing_cap_breached: bool | None = None,
) -> RollResult:
    """§15's roll math exactly: a=gA'Σ gA, b=gA'Σ g0,
    c=g0'Σ g0 - (g0+nD*gD)'Σ(g0+nD*gD), n_A_max=floor((-b+sqrt(b²-ac))/a).
    Prohibited on a negative discriminant, n_A_max<1, a rising ES, or a
    breached sizing cap — and, matching the rest of this engine, on an
    UNRESOLVED (None) ES/cap check too: the roll is never permitted on
    "we haven't checked yet."
    """
    gA, gD = g_new_per_contract, g_old_per_contract
    a = _quad_form(gA, sigma)
    b = _dot(gA, _matvec(sigma, g0))
    g_with_old = [g0_i + n_old_contracts * gD_i for g0_i, gD_i in zip(g0, gD)]
    c = _quad_form(g0, sigma) - _quad_form(g_with_old, sigma)
    discriminant = b * b - a * c

    if a == 0 or discriminant < 0:
        return RollResult(0, discriminant, False, "discriminant negative or degenerate — no real solution")

    n_a_max = math.floor((-b + math.sqrt(discriminant)) / a)
    if n_a_max < 1:
        return RollResult(n_a_max, discriminant, False, f"n_A_max={n_a_max} < 1")
    if es_rises is None or any_sizing_cap_breached is None:
        return RollResult(n_a_max, discriminant, False, "expected-shortfall / sizing-cap checks not yet evaluated")
    if es_rises:
        return RollResult(n_a_max, discriminant, False, "expected shortfall would rise")
    if any_sizing_cap_breached:
        return RollResult(n_a_max, discriminant, False, "a sizing cap would be breached")
    return RollResult(n_a_max, discriminant, True, f"n_A_max={n_a_max}, all roll conditions clear")
