"""Small price-series helpers shared across the engine. All series are
ascending by date (oldest first), matching engine.sources' FRED convention.
"""
from __future__ import annotations

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
