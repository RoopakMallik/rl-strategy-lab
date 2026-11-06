"""Features: no look-ahead, and both feature sets share the same trading price."""
import numpy as np
import pandas as pd
import pytest

from src.market_data.feature_engineering import WARMUP_DAYS, build_features, feature_columns


@pytest.fixture
def prices():
    rng = np.random.default_rng(0)
    n = 120
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    open_ = close * (1 + rng.normal(0, 0.005, n))
    return pd.DataFrame({
        "date": pd.bdate_range("2024-01-01", periods=n).date,
        "open": open_,
        "high": np.maximum(open_, close) * 1.01,
        "low": np.minimum(open_, close) * 0.99,
        "close": close,
        "volume": rng.integers(1_000_000, 5_000_000, n),
    })


@pytest.mark.parametrize("feature_set", ["standard", "indicators"])
def test_no_lookahead(prices, feature_set):
    """Features up to day t are identical whether or not later days exist."""
    full = build_features(prices, feature_set)
    cut = 90
    partial = build_features(prices.iloc[:cut], feature_set)
    common = partial.index
    pd.testing.assert_frame_equal(full.loc[common], partial)


def test_both_sets_trade_on_close(prices):
    std = build_features(prices, "standard")
    ind = build_features(prices, "indicators")
    assert list(std.index) == list(ind.index), "both feature sets must cover the same days"
    pd.testing.assert_series_equal(std["close"], ind["close"])
    assert set(feature_columns("standard")) < set(feature_columns("indicators"))


def test_features_are_finite_and_scaled(prices):
    f = build_features(prices, "indicators")
    assert np.isfinite(f[feature_columns("indicators")].to_numpy()).all()
    assert f["rsi_scaled"].between(-1, 1).all()
    assert f["obv_flow"].between(-1, 1).all()


def test_input_not_modified(prices):
    before = prices.copy()
    build_features(prices, "indicators")
    pd.testing.assert_frame_equal(prices, before)


def test_unchanged_closes_keep_every_day(prices):
    """Real data has days where the close repeats exactly (INTC 2025-01-14); none may be dropped."""
    flat = prices.copy()
    flat.loc[60:65, "close"] = flat.loc[59, "close"]
    flat["open"] = flat["close"]
    flat["high"], flat["low"] = flat["close"] * 1.01, flat["close"] * 0.99
    std = build_features(flat, "standard")
    ind = build_features(flat, "indicators")
    assert list(std.index) == list(ind.index)
    assert len(ind) == len(flat) - WARMUP_DAYS  # only the warm-up is removed


def test_missing_value_after_warmup_raises(prices):
    broken = prices.copy().astype({"close": float})
    broken.loc[80, "close"] = np.nan
    with pytest.raises(ValueError, match="missing after the warm-up"):
        build_features(broken, "indicators")
