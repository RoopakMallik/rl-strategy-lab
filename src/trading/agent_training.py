"""Train one agent, and play any policy (a trained agent or buy-and-hold) over a date range.

Agents and buy-and-hold go through the same TradingEnvironment, so they pay the same fees on
the same days. Nothing here touches the database: see experiment_grid.py and results_store.py.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
from stable_baselines3 import A2C, DQN, PPO
from stable_baselines3.common.base_class import BaseAlgorithm

from ..market_data.price_history import MarketData
from ..settings import TradingSettings
from .performance_metrics import PerformanceSummary, summarize_performance
from .trading_environment import TradingAction, TradingEnvironment, play_episode

ALGORITHM_CLASSES: dict[str, type[BaseAlgorithm]] = {"A2C": A2C, "DQN": DQN, "PPO": PPO}


@dataclass(frozen=True)
class EpisodeResult:
    """One policy played over one date range. Daily lists are aligned with `dates`."""
    dates: list[date]
    equity: np.ndarray
    in_position: list[bool]
    trade_count: int
    round_trip_returns: list[float]
    action_counts: dict[str, int]

    @property
    def period_start(self) -> date:
        return self.dates[0]

    @property
    def period_end(self) -> date:
        return self.dates[-1]

    def summarize(self, annual_risk_free_rate: float) -> PerformanceSummary:
        return summarize_performance(self.equity, self.in_position, self.trade_count,
                                     self.round_trip_returns, annual_risk_free_rate)


def build_environment(market: MarketData, first: date, last: date, trading: TradingSettings) -> TradingEnvironment:
    first_day, last_day = market.trading_day_range(first, last, trading.observation_window_days)
    return TradingEnvironment(market.close, market.features, first_day, last_day,
                              trading.observation_window_days, trading.buy_fee_rate, trading.sell_fee_rate)


def train_agent(algorithm: str, market: MarketData, train_start: date, train_end: date,
                trading: TradingSettings, seed: int, timesteps: int) -> tuple[BaseAlgorithm, float]:
    """Returns the trained model and the training time in seconds. CPU, so a seed is reproducible."""
    env = build_environment(market, train_start, train_end, trading)
    model = ALGORITHM_CLASSES[algorithm]("MlpPolicy", env, seed=seed, device="cpu", verbose=0)
    started = time.perf_counter()
    model.learn(total_timesteps=timesteps)
    return model, time.perf_counter() - started


def load_agent(algorithm: str, model_path: Path) -> BaseAlgorithm:
    return ALGORITHM_CLASSES[algorithm].load(model_path, device="cpu")


def evaluate_agent(model: BaseAlgorithm, market: MarketData, first: date, last: date,
                   trading: TradingSettings) -> EpisodeResult:
    env = build_environment(market, first, last, trading)
    return _episode_result(play_episode(env, lambda obs: int(model.predict(obs, deterministic=True)[0])), market)


def evaluate_buy_and_hold(market: MarketData, first: date, last: date, trading: TradingSettings) -> EpisodeResult:
    """Buy at the first close, hold, and sell at the last close (one round trip, both fees)."""
    env = build_environment(market, first, last, trading)
    return _episode_result(play_episode(env, lambda obs: TradingAction.BUY), market)


def _episode_result(env: TradingEnvironment, market: MarketData) -> EpisodeResult:
    records = env.daily_records
    actions = [r.action for r in records if r.action is not None]
    return EpisodeResult(
        dates=[market.dates[r.day_index] for r in records],
        equity=np.array([r.equity for r in records]),
        in_position=[r.in_position for r in records],
        trade_count=env.trade_count,
        round_trip_returns=list(env.completed_trade_returns),
        action_counts={a.name: actions.count(a.name) for a in TradingAction},
    )
