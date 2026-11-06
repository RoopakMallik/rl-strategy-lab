"""Download daily OHLCV from Yahoo Finance and upsert it into `daily_prices`.

    python -m src.market_data.price_download            # full history from HISTORY_START (safe to re-run)
    python -m src.market_data.price_download --refresh  # new days, re-checking the last week

Only completed trading days are stored (up to yesterday, or HISTORY_END): today's bar may still
be trading. A refresh re-downloads the last week; if those stored closes changed, a split or
dividend re-adjusted the history, so the ticker's full history is downloaded again.

Columns are selected BY NAME. The thesis notebook renamed them by position, but yfinance
returns them as Close, High, Low, Open, Volume, which silently swapped Open and Close.
Prices are split- and dividend-adjusted (auto_adjust=True), so the NVDA 10:1 split in
June 2024 does not look like a 90% crash.
"""
from __future__ import annotations

import argparse
import time
from datetime import date, timedelta

import pandas as pd
import yfinance as yf

from ..database import connect_as_writer
from ..settings import load_settings

YFINANCE_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]
DOWNLOAD_ATTEMPTS = 3
REFRESH_OVERLAP_DAYS = 7          # calendar days re-downloaded before the latest stored day
READJUSTMENT_TOLERANCE = 0.005    # a stored close differing by more than 0.5% means re-adjusted history

UPSERT_DAILY_PRICE = """
INSERT INTO daily_prices (ticker, date, open, high, low, close, volume, fetched_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, now())
ON CONFLICT (ticker, date) DO UPDATE SET
  open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
  close = EXCLUDED.close, volume = EXCLUDED.volume, fetched_at = now()
"""


def normalize_yfinance_frame(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Turn a yfinance frame (flat or MultiIndex columns, any order) into tidy rows."""
    frame = raw.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        # One ticker per download: keep only the level holding the price names (Close, Open, ...).
        level = next(i for i in range(frame.columns.nlevels) if "Close" in frame.columns.get_level_values(i))
        frame.columns = frame.columns.get_level_values(level)
    missing = [c for c in YFINANCE_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"{ticker}: yfinance response is missing columns {missing}; got {list(frame.columns)}")
    frame = frame[YFINANCE_COLUMNS].dropna(how="any")
    frame.index = pd.to_datetime(frame.index).date
    tidy = pd.DataFrame({
        "ticker": ticker,
        "date": frame.index,
        "open": frame["Open"].astype(float).values,
        "high": frame["High"].astype(float).values,
        "low": frame["Low"].astype(float).values,
        "close": frame["Close"].astype(float).values,
        "volume": frame["Volume"].astype("int64").values,
    })
    return tidy.sort_values("date").reset_index(drop=True)


def download_daily_prices(ticker: str, first_day: date, last_day: date) -> pd.DataFrame:
    """yfinance is unofficial and sometimes rate-limits or returns nothing, so retry with backoff."""
    end_exclusive = last_day + timedelta(days=1)  # yfinance treats `end` as exclusive
    last_error: Exception | None = None
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            raw = yf.download(ticker, start=first_day.isoformat(), end=end_exclusive.isoformat(), interval="1d",
                              auto_adjust=True, actions=False, progress=False, multi_level_index=False)
            if raw is not None and not raw.empty:
                rows = normalize_yfinance_frame(raw, ticker)
                rows = rows[(rows["date"] >= first_day) & (rows["date"] <= last_day)]  # Yahoo may pad either end
                if not rows.empty:
                    return rows
            last_error = RuntimeError("empty response")
        except Exception as exc:  # network errors, rate limits
            last_error = exc
        time.sleep(2 ** attempt)
    raise RuntimeError(f"{ticker}: download failed after {DOWNLOAD_ATTEMPTS} attempts: {last_error}")


def last_completed_day(history_end: date | None) -> date:
    """HISTORY_END if set; otherwise yesterday, because today's bar may still be trading."""
    return history_end or date.today() - timedelta(days=1)


def history_was_readjusted(conn, ticker: str, downloaded: pd.DataFrame) -> bool:
    """True if re-downloaded days no longer match the stored closes (a split or dividend changed
    the adjustment of past prices), so the stored history must be replaced."""
    stored = conn.execute("SELECT date, close FROM daily_prices WHERE ticker = %s AND date >= %s",
                          (ticker, downloaded["date"].min())).fetchall()
    stored_close = {row["date"]: row["close"] for row in stored}
    return any(abs(close / stored_close[day] - 1) > READJUSTMENT_TOLERANCE
               for day, close in zip(downloaded["date"], downloaded["close"]) if day in stored_close)


def save_daily_prices(conn, ticker: str, rows: pd.DataFrame, mode: str, requested_from: date) -> None:
    """Upsert the rows and log the download, together."""
    with conn.transaction():
        with conn.cursor() as cur:
            cur.executemany(UPSERT_DAILY_PRICE, list(rows.itertuples(index=False, name=None)))
        conn.execute(
            """INSERT INTO price_ingest_log (ticker, ingest_mode, requested_from_date, rows_upserted, latest_price_date)
               VALUES (%s, %s, %s, %s, %s)""",
            (ticker, mode, requested_from, len(rows), rows["date"].max()),
        )
    print(f"{ticker}: {mode} upserted {len(rows)} rows, {rows['date'].min()} to {rows['date'].max()}")


def store_price_history(refresh: bool = False) -> None:
    settings = load_settings().market_data
    last_day = last_completed_day(settings.history_end)
    with connect_as_writer() as conn:
        for ticker in settings.tickers:
            latest = conn.execute("SELECT max(date) AS latest FROM daily_prices WHERE ticker = %s",
                                  (ticker,)).fetchone()["latest"]
            if not refresh or latest is None:
                save_daily_prices(conn, ticker, download_daily_prices(ticker, settings.history_start, last_day),
                                  "full", settings.history_start)
                continue
            # Re-download the last few stored days too: they confirm the stored adjustment still holds.
            first_day = latest - timedelta(days=REFRESH_OVERLAP_DAYS)
            try:
                rows = download_daily_prices(ticker, first_day, last_day)
            except RuntimeError:  # weekend, holiday, or Yahoo briefly unavailable
                print(f"{ticker}: nothing new after {latest}")
                continue
            if history_was_readjusted(conn, ticker, rows):
                print(f"{ticker}: stored prices no longer match Yahoo's adjustment; downloading full history")
                first_day = settings.history_start
                save_daily_prices(conn, ticker, download_daily_prices(ticker, first_day, last_day), "full", first_day)
            else:
                save_daily_prices(conn, ticker, rows, "refresh", first_day)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="fetch new days only, re-checking the last week")
    store_price_history(refresh=parser.parse_args().refresh)


if __name__ == "__main__":
    main()
