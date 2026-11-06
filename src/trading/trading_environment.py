"""Buy / Sell / Hold trading environment (long-only, all-in or all-out).

Timing, one step per trading day t:
  1. The agent sees features for days t-w+1 .. t and whether it currently holds the stock.
  2. It chooses an action, executed at day t's close.
       Buy  -> hold the stock.     Sell -> hold cash.     Hold -> keep the current position.
     Buying while holding, or selling while in cash, is the same as Hold and costs nothing.
  3. Reward = log(1 - fee) if the position changed, plus log(close[t+1] / close[t]) if holding.
     On the last step, an open position is sold (and pays the sell fee), so every episode ends
     in cash, exactly like the buy-and-hold baseline's single round trip.

Because rewards are log returns, sum(rewards) == log(final_equity / starting_equity). The agent
optimises exactly the profit we report.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Callable

import gymnasium as gym
import numpy as np
from gymnasium import spaces


class TradingAction(IntEnum):
    HOLD = 0
    BUY = 1
    SELL = 2


@dataclass(frozen=True)
class DailyRecord:
    """State at the close of trading day `day_index`, after that day's step."""
    day_index: int
    equity: float
    in_position: bool       # holding the stock overnight from this close
    action: str | None      # action chosen at this close (None on the last day)


class TradingEnvironment(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, close: np.ndarray, features: np.ndarray, first_day: int, last_day: int,
                 observation_window_days: int, buy_fee_rate: float, sell_fee_rate: float):
        """`close` and `features` cover the whole history (features row i = day i).

        The episode trades days first_day .. last_day (inclusive): decisions are made at the
        closes of first_day .. last_day-1, and the episode is valued at last_day's close.
        `first_day` may be inside the history so the first observation window uses earlier days.
        """
        super().__init__()
        close = np.asarray(close, dtype=np.float64)
        features = np.asarray(features, dtype=np.float32)
        if len(close) != len(features):
            raise ValueError("close and features must have the same length")
        if not (observation_window_days - 1 <= first_day < last_day < len(close)):
            raise ValueError("need observation_window_days-1 <= first_day < last_day < len(close): "
                             f"got {first_day}, {last_day}, {len(close)}")
        self.close, self.features = close, features
        self.first_day, self.last_day = first_day, last_day
        self.observation_window_days = observation_window_days
        self.buy_fee_rate, self.sell_fee_rate = buy_fee_rate, sell_fee_rate
        observation_size = observation_window_days * features.shape[1] + 1
        self.observation_space = spaces.Box(-np.inf, np.inf, shape=(observation_size,), dtype=np.float32)
        self.action_space = spaces.Discrete(len(TradingAction))
        self.reset()

    # -- gymnasium API -----------------------------------------------------------------------
    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        self.day = self.first_day
        self.in_position = False
        self.equity = 1.0
        self.trade_count = 0
        self.completed_trade_returns: list[float] = []   # net return of each buy -> sell round trip
        self._equity_at_entry = 1.0
        self.daily_records: list[DailyRecord] = []
        return self._observation(), self._info()

    def step(self, action: int):
        action = TradingAction(int(action))
        self.daily_records.append(DailyRecord(self.day, self.equity, self._wants_position(action), action.name))
        reward = 0.0
        if self._wants_position(action) != self.in_position:
            reward += self._trade()

        if self.in_position:
            reward += self._apply_growth(self.close[self.day + 1] / self.close[self.day])
        self.day += 1

        terminated = self.day >= self.last_day
        if terminated:
            if self.in_position:
                reward += self._trade()  # liquidate at the final close
            self.daily_records.append(DailyRecord(self.day, self.equity, False, None))
        return self._observation(), reward, terminated, False, self._info()

    # -- helpers -----------------------------------------------------------------------------
    def _wants_position(self, action: TradingAction) -> bool:
        return {TradingAction.BUY: True, TradingAction.SELL: False, TradingAction.HOLD: self.in_position}[action]

    def _apply_growth(self, factor: float) -> float:
        self.equity *= factor
        return float(np.log(factor))

    def _trade(self) -> float:
        """Flip the position and pay the fee. Returns the fee as a log reward."""
        buying = not self.in_position
        if buying:
            self._equity_at_entry = self.equity
        reward = self._apply_growth(1.0 - (self.buy_fee_rate if buying else self.sell_fee_rate))
        if not buying:
            self.completed_trade_returns.append(self.equity / self._equity_at_entry - 1.0)
        self.in_position = buying
        self.trade_count += 1
        return reward

    def _observation(self) -> np.ndarray:
        window = self.features[self.day - self.observation_window_days + 1: self.day + 1].ravel()
        return np.append(window, np.float32(self.in_position)).astype(np.float32)

    def _info(self) -> dict:
        return {"equity": self.equity, "in_position": self.in_position, "trade_count": self.trade_count,
                "day": self.day}


def play_episode(env: TradingEnvironment, choose_action: Callable[[np.ndarray], int]) -> TradingEnvironment:
    """Run one full episode with `choose_action(observation) -> action`. Returns the finished env."""
    observation, _ = env.reset()
    finished = False
    while not finished:
        observation, _, finished, _, _ = env.step(choose_action(observation))
    return env
