"""Turn raw prices into the numbers the agent sees.

Both feature sets use only past and current data (no look-ahead) and are scale-free, so a
$15 stock and a $180 stock look alike to the network. `close` is kept separately as the
trading price for BOTH feature sets.

standard   (5): close log return, open/high/low relative to close, log volume vs 20-day mean
indicators (8): standard + gap to SMA(12), RSI(14) rescaled, OBV(12-day change) / 12-day volume
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from finta import TA

from ..experiment_options import FEATURE_SETS

# The feature definitions are part of the experiment (they follow the thesis), so they are named
# constants here rather than settings: changing one changes what the results mean.
VOLUME_AVERAGE_DAYS = 20
SMA_PERIOD = 12
RSI_PERIOD = 14
OBV_FLOW_DAYS = 12
WARMUP_DAYS = RSI_PERIOD * 2

STANDARD_FEATURES = ["close_log_return", "open_vs_close", "high_vs_close", "low_vs_close", "log_volume_vs_average"]
INDICATOR_FEATURES = STANDARD_FEATURES + ["close_vs_sma", "rsi_scaled", "obv_flow"]


def feature_columns(feature_set: str) -> list[str]:
    if feature_set not in FEATURE_SETS:
        raise ValueError(f"feature_set must be one of {FEATURE_SETS}")
    return INDICATOR_FEATURES if feature_set == "indicators" else STANDARD_FEATURES


def build_features(prices: pd.DataFrame, feature_set: str) -> pd.DataFrame:
    """`prices` has columns date, open, high, low, close, volume.

    Returns a frame indexed by date with `close` plus the feature columns. The warm-up rows at
    the start of history are dropped; a missing value after the warm-up raises, because silently
    dropping it would give the two feature sets different trading days.
    """
    columns = feature_columns(feature_set)
    daily = prices.sort_values("date").set_index("date")
    features = pd.DataFrame(index=daily.index)
    features["close"] = daily["close"]
    features["close_log_return"] = np.log(daily["close"]).diff()
    features["open_vs_close"] = daily["open"] / daily["close"] - 1
    features["high_vs_close"] = daily["high"] / daily["close"] - 1
    features["low_vs_close"] = daily["low"] / daily["close"] - 1
    features["log_volume_vs_average"] = np.log(
        daily["volume"].clip(lower=1) / daily["volume"].rolling(VOLUME_AVERAGE_DAYS).mean())

    if feature_set == "indicators":
        # finta expects lowercase ohlcv and writes into its input, so each call gets a copy.
        ohlcv = daily[["open", "high", "low", "close", "volume"]]
        sma = TA.SMA(ohlcv.copy(), SMA_PERIOD)
        rsi = TA.RSI(ohlcv.copy(), RSI_PERIOD)
        features["close_vs_sma"] = daily["close"] / sma - 1
        features["rsi_scaled"] = (rsi - 50) / 50  # 0..100 -> -1..1
        features["obv_flow"] = on_balance_volume_flow(daily["close"], daily["volume"], OBV_FLOW_DAYS)

    # Same warm-up for both feature sets, so they train and test on exactly the same days.
    # (finta's RSI uses an expanding EWM from the first row, so its first values are unstable.)
    selected = features[["close", *columns]].iloc[WARMUP_DAYS:].replace([np.inf, -np.inf], np.nan)
    missing = selected[selected.isna().any(axis=1)]
    if not missing.empty:
        raise ValueError(f"{feature_set} features are missing after the warm-up on {len(missing)} days, "
                         f"first {missing.index[0]}: {missing.columns[missing.isna().any()].tolist()}")
    return selected


def on_balance_volume_flow(close: pd.Series, volume: pd.Series, days: int) -> pd.Series:
    """Change in on-balance volume over `days`, divided by total volume over `days`: -1..1.

    On-balance volume adds the day's volume on an up close, subtracts it on a down close and
    adds nothing on an unchanged close. (finta's OBV returns NaN on unchanged closes, which
    happen on real data, e.g. INTC on 2025-01-14, so it is computed here.)
    """
    signed_volume = np.sign(close.diff()).fillna(0) * volume
    return signed_volume.rolling(days).sum() / volume.rolling(days).sum()
