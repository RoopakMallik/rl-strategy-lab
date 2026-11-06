"""Performance metrics. Pure functions of an equity curve: no database, no settings.

Conventions (also used by the database, tools and dashboard):
- Returns and rates are fractions: 0.12 means 12%.
- max_drawdown is the largest peak-to-trough fall as a POSITIVE fraction: 0.25 means -25%.
- sharpe_ratio is annualised from daily simple returns: mean excess / std * sqrt(252).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

TRADING_DAYS_PER_YEAR = 252


def total_return(equity: np.ndarray) -> float:
    return float(equity[-1] / equity[0] - 1.0)


def daily_returns(equity: np.ndarray) -> np.ndarray:
    equity = np.asarray(equity, dtype=float)
    return equity[1:] / equity[:-1] - 1.0


def sharpe_ratio(equity: np.ndarray, annual_risk_free_rate: float = 0.0) -> float | None:
    """None when it is undefined: fewer than two returns, or no variation (e.g. always in cash)."""
    returns = daily_returns(equity)
    if len(returns) < 2:
        return None
    volatility = returns.std(ddof=1)
    if volatility < 1e-12:
        return None
    daily_risk_free = (1.0 + annual_risk_free_rate) ** (1.0 / TRADING_DAYS_PER_YEAR) - 1.0
    return float((returns.mean() - daily_risk_free) / volatility * np.sqrt(TRADING_DAYS_PER_YEAR))


def max_drawdown(equity: np.ndarray) -> float:
    equity = np.asarray(equity, dtype=float)
    running_peak = np.maximum.accumulate(equity)
    return float(np.max(1.0 - equity / running_peak))


def win_rate(round_trip_returns: list[float]) -> float | None:
    """Share of completed buy -> sell round trips that made money after fees. None if no trips."""
    if not round_trip_returns:
        return None
    return float(np.mean(np.asarray(round_trip_returns) > 0))


def exposure(in_position: list[bool]) -> float:
    """Share of overnight intervals spent holding the stock (the last day has no interval)."""
    intervals = in_position[:-1]
    return float(np.mean(intervals)) if intervals else 0.0


@dataclass(frozen=True)
class PerformanceSummary:
    trading_days: int
    total_return: float
    sharpe_ratio: float | None
    max_drawdown: float
    trade_count: int
    round_trip_count: int
    win_rate: float | None
    exposure: float


def summarize_performance(equity: np.ndarray, in_position: list[bool], trade_count: int,
                          round_trip_returns: list[float], annual_risk_free_rate: float) -> PerformanceSummary:
    return PerformanceSummary(
        trading_days=len(equity),
        total_return=total_return(equity),
        sharpe_ratio=sharpe_ratio(equity, annual_risk_free_rate),
        max_drawdown=max_drawdown(equity),
        trade_count=trade_count,
        round_trip_count=len(round_trip_returns),
        win_rate=win_rate(round_trip_returns),
        exposure=exposure(in_position),
    )


def block_bootstrap_interval(daily_values: np.ndarray, confidence_level: float, samples: int,
                             block_days: int, random_seed: int) -> tuple[float, float]:
    """Confidence interval for the SUM of `daily_values`, by moving-block bootstrap.

    Days are resampled in blocks of consecutive days, so short runs of correlated returns stay
    together. Used on daily log-return differences (strategy minus buy-and-hold): the sum is the
    log of how much more (or less) money the strategy ended with.
    """
    values = np.asarray(daily_values, dtype=float)
    days = len(values)
    if days == 0:
        raise ValueError("need at least one daily value")
    block_days = max(1, min(block_days, days))
    blocks_needed = int(np.ceil(days / block_days))
    rng = np.random.default_rng(random_seed)
    block_starts = rng.integers(0, days - block_days + 1, size=(samples, blocks_needed))
    resampled = values[(block_starts[:, :, None] + np.arange(block_days)).reshape(samples, -1)[:, :days]]
    sums = resampled.sum(axis=1)
    tail = (1.0 - confidence_level) / 2.0
    low, high = np.quantile(sums, [tail, 1.0 - tail])
    return float(low), float(high)
