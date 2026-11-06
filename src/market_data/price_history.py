"""Load one ticker's prices from Postgres and turn them into what the trading environment needs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from ..database import connect_as_reader
from .feature_engineering import build_features, feature_columns


def load_daily_prices(ticker: str) -> pd.DataFrame:
    with connect_as_reader() as conn:
        rows = conn.execute(
            "SELECT date, open, high, low, close, volume FROM daily_prices WHERE ticker = %s ORDER BY date",
            (ticker,),
        ).fetchall()
    if not rows:
        raise RuntimeError(f"No prices for {ticker}. Run `make ingest` first.")
    return pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])


@dataclass(frozen=True)
class MarketData:
    """One ticker and feature set, aligned by trading day: row i of every array is dates[i]."""
    ticker: str
    feature_set: str
    dates: list[date]
    close: np.ndarray
    features: np.ndarray

    def trading_day_range(self, first: date, last: date, observation_window_days: int) -> tuple[int, int]:
        """Indexes of the first and last trading day inside [first, last].

        The first index is at least `observation_window_days - 1`, so the opening observation
        window only uses days that exist.
        """
        inside = [i for i, d in enumerate(self.dates) if first <= d <= last]
        if len(inside) < 2:
            raise ValueError(f"{self.ticker}: fewer than 2 trading days between {first} and {last}")
        return max(inside[0], observation_window_days - 1), inside[-1]


def load_market_data(ticker: str, feature_set: str) -> MarketData:
    features = build_features(load_daily_prices(ticker), feature_set)
    return MarketData(ticker=ticker, feature_set=feature_set, dates=list(features.index),
                      close=features["close"].to_numpy(),
                      features=features[feature_columns(feature_set)].to_numpy())
