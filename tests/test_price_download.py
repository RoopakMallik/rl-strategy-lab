"""yfinance columns are mapped by name, whatever order they arrive in."""
import pandas as pd

from src.market_data.price_download import normalize_yfinance_frame


def yfinance_like_frame(multi: bool) -> pd.DataFrame:
    # yfinance's real order: Close, High, Low, Open, Volume (the source of the thesis swap).
    data = {"Close": [139.77], "High": [152.73], "Low": [139.64], "Open": [152.63], "Volume": [351782200]}
    df = pd.DataFrame(data, index=pd.to_datetime(["2025-01-07"]))
    if multi:
        df.columns = pd.MultiIndex.from_product([df.columns, ["NVDA"]], names=["Price", "Ticker"])
    return df


def test_maps_columns_by_name_flat():
    row = normalize_yfinance_frame(yfinance_like_frame(multi=False), "NVDA").iloc[0]
    assert row["open"] == 152.63 and row["close"] == 139.77


def test_maps_columns_by_name_multiindex():
    row = normalize_yfinance_frame(yfinance_like_frame(multi=True), "NVDA").iloc[0]
    assert row["open"] == 152.63 and row["close"] == 139.77
    assert row["ticker"] == "NVDA"
