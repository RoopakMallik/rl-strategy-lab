"""Seed-averaged strategy vs buy-and-hold, on curves small enough to check by hand."""
import numpy as np
import pandas as pd
import pytest

from src.settings import AnalysisSettings
from src.trading.strategy_comparison import compare_with_buy_and_hold

ANALYSIS = AnalysisSettings(risk_free_rate=0.0, confidence_level=0.95, bootstrap_samples=2000,
                            bootstrap_block_days=2, bootstrap_random_seed=0)
DATES = pd.Index(pd.date_range("2025-01-01", periods=7).date)  # 3 blocks of 2 days + 1


def test_excess_return_uses_mean_of_seed_curves():
    seeds = pd.DataFrame({0: [1.0, 1.1, 1.2, 1.2, 1.25, 1.3, 1.3],
                          1: [1.0, 0.9, 1.0, 1.0, 1.05, 1.1, 1.1]}, index=DATES)  # mean ends 1.2
    baseline = pd.Series([1.0, 1.0, 1.05, 1.02, 0.98, 1.0, 1.0], index=DATES)
    result = compare_with_buy_and_hold(seeds, baseline, ANALYSIS)
    assert result.strategy_return == pytest.approx(0.2)
    assert result.buy_and_hold_return == pytest.approx(0.0)
    assert result.excess_return == pytest.approx(1.2 / 1.0 - 1)
    assert result.seed_count == 2 and result.seeds_beating_buy_and_hold == 2
    assert result.excess_return_ci_low <= result.excess_return <= result.excess_return_ci_high


def test_a_small_noisy_edge_does_not_count_as_beating():
    rng = np.random.default_rng(3)
    dates = pd.Index(pd.date_range("2025-01-01", periods=250).date)
    market = np.cumprod(1 + rng.normal(0.0005, 0.02, 250))
    strategy = market * np.cumprod(1 + rng.normal(0.0002, 0.01, 250))   # +0.02%/day, very noisy
    result = compare_with_buy_and_hold(pd.DataFrame({0: strategy}, index=dates), pd.Series(market, index=dates),
                                       ANALYSIS)
    assert result.excess_return_ci_low < 0 < result.excess_return_ci_high
    assert not result.beats_buy_and_hold


def test_too_few_days_for_an_interval_is_refused():
    short = DATES[:6]  # needs 3 blocks x 2 days + 1 = 7
    curve = pd.Series([1.0, 1.01, 1.02, 1.03, 1.04, 1.05], index=short)
    with pytest.raises(ValueError, match="trading days"):
        compare_with_buy_and_hold(pd.DataFrame({0: curve}), curve, ANALYSIS)


def test_seeds_on_different_days_are_refused():
    seeds = pd.DataFrame({0: [1.0] * 7, 1: [1.0] * 6 + [None]}, index=DATES)
    with pytest.raises(ValueError, match="different days"):
        compare_with_buy_and_hold(seeds, pd.Series([1.0] * 7, index=DATES), ANALYSIS)


def test_rejects_misaligned_dates():
    seeds = pd.DataFrame({0: [1.0] * 7}, index=DATES)
    with pytest.raises(ValueError, match="baseline"):
        compare_with_buy_and_hold(seeds, pd.Series([1.0] * 6, index=DATES[:6]), ANALYSIS)
