"""Small price-series helpers shared across the engine. All series are
ascending by date (oldest first), matching engine.sources' FRED convention.
"""
from __future__ import annotations

import math
import statistics
from typing import Sequence


def sma(values: Sequence[float], window: int) -> float:
    """Simple moving average of the trailing `window` values (inclusive of
    the most recent one)."""
    if len(values) < window:
        raise ValueError(f"need >= {window} values, got {len(values)}")
    return statistics.fmean(values[-window:])


def rolling_max(values: Sequence[float], window: int) -> float:
    if len(values) < window:
        raise ValueError(f"need >= {window} values, got {len(values)}")
    return max(values[-window:])


def pct_change(values: Sequence[float], lag: int) -> float:
    """% change from `lag` sessions ago to the latest value."""
    if len(values) <= lag:
        raise ValueError(f"need > {lag} values, got {len(values)}")
    base = values[-1 - lag]
    if base == 0:
        raise ValueError("base value is zero")
    return (values[-1] / base - 1) * 100.0


def daily_returns(values: Sequence[float]) -> list[float]:
    """Day-over-day returns as fractions (e.g. -0.05, not -5.0)."""
    return [values[i] / values[i - 1] - 1 for i in range(1, len(values)) if values[i - 1] != 0]


def rsi_wilder(values: Sequence[float], period: int = 14) -> float:
    """Wilder's RSI over the whole series: a simple average of the first
    `period` changes seeds the averages, then Wilder's smoothing runs to the
    latest value. Needs well over `period` values to converge — pass a year
    of closes, not fifteen."""
    if len(values) <= period:
        raise ValueError(f"need > {period} values, got {len(values)}")
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    avg_gain = sum(max(c, 0.0) for c in changes[:period]) / period
    avg_loss = sum(max(-c, 0.0) for c in changes[:period]) / period
    for c in changes[period:]:
        avg_gain = (avg_gain * (period - 1) + max(c, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-c, 0.0)) / period
    if avg_loss == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def realized_vol(values: Sequence[float], window: int = 30, periods_per_year: int = 252,
                 trim_largest: int = 0) -> float:
    """Annualized close-to-close volatility of log returns over the trailing
    `window` returns, as a fraction (0.35 = 35%), directly comparable to an
    option's implied volatility. `trim_largest` drops that many of the
    biggest absolute moves first, so one earnings gap inside the window
    doesn't dominate the estimate."""
    if len(values) <= window:
        raise ValueError(f"need > {window} values, got {len(values)}")
    if not 0 <= trim_largest <= window - 2:
        raise ValueError(f"trim_largest={trim_largest} leaves too few returns")
    tail = values[-(window + 1):]
    logs = [math.log(tail[i] / tail[i - 1]) for i in range(1, len(tail))]
    if trim_largest:
        logs = sorted(logs, key=abs)[:-trim_largest]
    return statistics.stdev(logs) * math.sqrt(periods_per_year)
