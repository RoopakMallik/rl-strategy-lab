"""Metrics on hand-checked equity curves (build step 5)."""
import numpy as np
import pytest

from src.trading.performance_metrics import (block_bootstrap_interval, exposure, max_drawdown, sharpe_ratio,
                                             summarize_performance, total_return, win_rate)

# 1.00 -> 1.10 (+10%) -> 0.99 (-10%) -> 1.089 (+10%) -> 1.188 (+9.09%)
EQUITY = np.array([1.0, 1.1, 0.99, 1.089, 1.188])


def test_total_return():
    assert total_return(EQUITY) == pytest.approx(0.188)


def test_max_drawdown_is_positive_peak_to_trough_fraction():
    assert max_drawdown(EQUITY) == pytest.approx(0.10)       # 1.10 -> 0.99
    assert max_drawdown(np.array([1.0, 1.2, 1.3])) == 0.0     # never below a peak
    assert max_drawdown(np.array([2.0, 1.0, 1.5, 0.5])) == pytest.approx(0.75)


def test_sharpe_ratio_by_hand():
    returns = np.array([0.10, -0.10, 0.10, 1.188 / 1.089 - 1])
    expected = returns.mean() / returns.std(ddof=1) * np.sqrt(252)
    assert sharpe_ratio(EQUITY) == pytest.approx(expected)


def test_sharpe_ratio_subtracts_daily_risk_free_rate():
    daily_risk_free = 1.05 ** (1 / 252) - 1
    returns = EQUITY[1:] / EQUITY[:-1] - 1
    expected = (returns.mean() - daily_risk_free) / returns.std(ddof=1) * np.sqrt(252)
    assert sharpe_ratio(EQUITY, annual_risk_free_rate=0.05) == pytest.approx(expected)


def test_sharpe_ratio_undefined_without_variation():
    assert sharpe_ratio(np.ones(10)) is None        # always in cash
    assert sharpe_ratio(np.array([1.0, 1.1])) is None  # one return


def test_win_rate_and_exposure():
    assert win_rate([0.05, -0.01, 0.02, 0.0]) == pytest.approx(0.5)  # break-even is not a win
    assert win_rate([]) is None
    assert exposure([True, True, False, False, False]) == pytest.approx(0.5)  # last day ignored
    assert exposure([False]) == 0.0


def test_summary_combines_the_metrics():
    summary = summarize_performance(EQUITY, [True, True, True, True, False], trade_count=2,
                                    round_trip_returns=[0.188], annual_risk_free_rate=0.0)
    assert summary.trading_days == 5
    assert summary.total_return == pytest.approx(0.188)
    assert summary.round_trip_count == 1 and summary.win_rate == 1.0 and summary.exposure == 1.0


def test_bootstrap_interval_contains_the_observed_sum_and_is_reproducible():
    rng = np.random.default_rng(1)
    daily = rng.normal(0.001, 0.02, 250)
    low, high = block_bootstrap_interval(daily, 0.95, 4000, 10, random_seed=0)
    assert low < daily.sum() < high
    assert (low, high) == block_bootstrap_interval(daily, 0.95, 4000, 10, random_seed=0)


def test_bootstrap_interval_excludes_zero_for_a_clear_edge():
    daily = np.full(250, 0.002) + np.random.default_rng(2).normal(0, 0.001, 250)
    low, _ = block_bootstrap_interval(daily, 0.95, 4000, 10, random_seed=0)
    assert low > 0
