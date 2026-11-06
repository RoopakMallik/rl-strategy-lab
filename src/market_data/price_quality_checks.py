"""Price data checks: test the stored prices and write a dated JSON report.

    python -m src.market_data.price_quality_checks

Each check records what was tested, the expected value, the observed value and pass/fail,
so a reader can see exactly why the data is trusted.
"""
from __future__ import annotations

import json
from datetime import date, datetime

import pandas as pd

from ..settings import PROJECT_ROOT, load_settings
from .price_history import load_daily_prices

# Known closes, split-adjusted. Source: Yahoo Finance as published at the time; they also match
# the thesis CSVs, where these values sit in the "Open" column because of the column swap.
# The tolerance covers later dividend adjustments. Add a row when you add a ticker.
KNOWN_CLOSES = [
    ("NVDA", "2025-01-02", 138.3),
    ("NVDA", "2025-01-07", 140.1),
    ("AMD", "2025-01-02", 120.6),
    ("INTC", "2025-01-02", 20.2),
]
KNOWN_CLOSE_TOLERANCE = 0.02
# 2025-01-07: NVDA opened near 153 and closed near 140. If Open and Close were swapped,
# close would be above open on this day.
OPEN_CLOSE_SWAP_CHECK = ("NVDA", "2025-01-07")
MAX_CALENDAR_GAP_DAYS = 4      # weekend plus a Monday or Friday holiday
MAX_ABS_DAILY_MOVE = 0.40      # an unadjusted 10:1 split shows as a -90% day
OHLC_TOLERANCE = 1e-6
TRADING_DAYS_PER_YEAR_RANGE = (240, 256)
START_GRACE_DAYS = 7           # HISTORY_START may fall on a weekend or holiday


def check_result(name: str, passed: bool, expected, observed, ticker: str | None = None) -> dict:
    return {"ticker": ticker, "check": name, "passed": bool(passed), "expected": expected, "observed": observed}


def check_ticker(ticker: str, history_start: date) -> list[dict]:
    prices = load_daily_prices(ticker)
    prices["date"] = pd.to_datetime(prices["date"])
    results = []

    years = (prices["date"].iloc[-1] - prices["date"].iloc[0]).days / 365.25
    low, high = TRADING_DAYS_PER_YEAR_RANGE
    results.append(check_result("rows per year about 252", low <= len(prices) / years <= high,
                                f"{low}-{high}", round(len(prices) / years, 1), ticker))

    first_day = prices["date"].iloc[0].date()
    results.append(check_result("starts at HISTORY_START",
                                first_day <= history_start + pd.Timedelta(days=START_GRACE_DAYS),
                                f"<= {history_start} + {START_GRACE_DAYS} days", str(first_day), ticker))

    largest_gap = int(prices["date"].diff().dt.days.max())
    results.append(check_result("no missing trading days", largest_gap <= MAX_CALENDAR_GAP_DAYS,
                                f"max gap <= {MAX_CALENDAR_GAP_DAYS} calendar days", largest_gap, ticker))

    open_close_low = prices[["open", "close"]].min(axis=1)
    open_close_high = prices[["open", "close"]].max(axis=1)
    inconsistent = int(((prices["low"] > open_close_low + OHLC_TOLERANCE) |
                        (prices["high"] < open_close_high - OHLC_TOLERANCE)).sum())
    results.append(check_result("low <= open,close <= high", inconsistent == 0, 0, inconsistent, ticker))

    not_positive = int((prices[["open", "high", "low", "close"]] <= 0).any(axis=1).sum())
    results.append(check_result("prices positive", not_positive == 0, 0, not_positive, ticker))

    largest_move = float(prices["close"].pct_change().abs().max())
    results.append(check_result("split-adjusted (no >40% daily move)", largest_move < MAX_ABS_DAILY_MOVE,
                                f"< {MAX_ABS_DAILY_MOVE:.0%}", f"{largest_move:.1%}", ticker))

    by_date = prices.set_index(prices["date"].dt.date)
    for known_ticker, day, expected_close in KNOWN_CLOSES:
        if known_ticker != ticker:
            continue
        day = date.fromisoformat(day)
        observed = round(float(by_date.loc[day, "close"]), 2) if day in by_date.index else None
        passed = observed is not None and abs(observed / expected_close - 1) <= KNOWN_CLOSE_TOLERANCE
        results.append(check_result(f"known close on {day}", passed,
                                    f"{expected_close} +/- {KNOWN_CLOSE_TOLERANCE:.0%}", observed, ticker))

    if ticker == OPEN_CLOSE_SWAP_CHECK[0]:
        day = date.fromisoformat(OPEN_CLOSE_SWAP_CHECK[1])
        row = by_date.loc[day] if day in by_date.index else None
        passed = row is not None and row["open"] > row["close"] * 1.05
        observed = None if row is None else {"open": round(float(row["open"]), 2), "close": round(float(row["close"]), 2)}
        results.append(check_result(f"Open/Close not swapped ({day})", passed, "open > close by > 5%", observed, ticker))
    return results


def run_price_checks() -> list[dict]:
    settings = load_settings().market_data
    return [result for ticker in settings.tickers for result in check_ticker(ticker, settings.history_start)]


def main() -> None:
    results = run_price_checks()
    reports_dir = load_settings().evaluation_reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "suite": "price_data",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "passed": sum(r["passed"] for r in results),
        "total": len(results),
        "checks": results,
    }
    path = reports_dir / f"price_data_checks_{date.today().isoformat()}.json"
    path.write_text(json.dumps(report, indent=2, default=str))
    for r in results:
        print(f"{'PASS' if r['passed'] else 'FAIL'}  {r['ticker'] or '':5} {r['check']}: "
              f"expected {r['expected']}, observed {r['observed']}")
    print(f"\n{report['passed']}/{report['total']} checks passed. Report: {path.relative_to(PROJECT_ROOT)}")
    if report["passed"] != report["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
