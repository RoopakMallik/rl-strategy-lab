"""Buy-and-hold and agent evaluation go through the same environment (no database needed)."""
from datetime import date, timedelta

import numpy as np
import pytest

from src.market_data.price_history import MarketData
from src.settings import TradingSettings
from src.trading.agent_training import evaluate_buy_and_hold, train_agent, evaluate_agent

TRADING = TradingSettings(buy_fee_rate=0.001, sell_fee_rate=0.002, observation_window_days=2)
DAYS = [date(2025, 1, 1) + timedelta(days=i) for i in range(12)]
CLOSE = np.array([50, 51, 52, 50, 53, 55, 54, 56, 58, 57, 59, 60], dtype=float)
MARKET = MarketData("TEST", "standard", DAYS, CLOSE, np.random.default_rng(0).normal(size=(12, 3)))


def test_buy_and_hold_is_one_round_trip_with_both_fees():
    episode = evaluate_buy_and_hold(MARKET, DAYS[2], DAYS[11], TRADING)
    expected = (1 - 0.001) * (CLOSE[11] / CLOSE[2]) * (1 - 0.002)
    assert episode.equity[-1] == pytest.approx(expected)
    assert episode.dates == DAYS[2:]
    assert episode.trade_count == 2 and episode.round_trip_returns == [pytest.approx(expected - 1)]
    assert episode.summarize(0.0).total_return == pytest.approx(expected - 1)


def test_buy_and_hold_starts_no_earlier_than_the_observation_window_allows():
    episode = evaluate_buy_and_hold(MARKET, DAYS[0], DAYS[5], TRADING)
    assert episode.period_start == DAYS[1]  # day 0 has no previous day for a 2-day window


def test_same_seed_gives_identical_agent():
    results = []
    for _ in range(2):
        model, _ = train_agent("PPO", MARKET, DAYS[1], DAYS[8], TRADING, seed=3, timesteps=256)
        results.append(evaluate_agent(model, MARKET, DAYS[8], DAYS[11], TRADING).equity)
    np.testing.assert_array_equal(*results)
