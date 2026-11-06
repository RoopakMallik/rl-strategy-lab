"""The trading rules behave exactly as documented in src/trading/trading_environment.py."""
import numpy as np
import pytest

from src.trading.trading_environment import TradingAction, TradingEnvironment, play_episode

FEE = 0.001
CLOSE = np.array([100, 101, 103, 102, 105, 107, 106, 110], dtype=float)
FEATURES = np.arange(len(CLOSE) * 2, dtype=np.float32).reshape(-1, 2)
BUY, SELL, HOLD = TradingAction.BUY, TradingAction.SELL, TradingAction.HOLD


def make_env(first_day=1, last_day=7, fee=FEE, features=FEATURES):
    return TradingEnvironment(CLOSE, features, first_day=first_day, last_day=last_day,
                              observation_window_days=2, buy_fee_rate=fee, sell_fee_rate=fee)


def run(env, actions):
    env.reset()
    rewards = []
    for action in actions:
        _, reward, finished, _, _ = env.step(action)
        rewards.append(reward)
        if finished:
            break
    return rewards


def test_buy_while_holding_is_a_free_hold():
    a, b = make_env(), make_env()
    run(a, [BUY, BUY, BUY, HOLD, HOLD, HOLD])
    run(b, [BUY, HOLD, HOLD, HOLD, HOLD, HOLD])
    assert a.equity == pytest.approx(b.equity)
    assert a.trade_count == b.trade_count == 2  # one buy, plus the forced sell at the end


def test_sell_while_in_cash_costs_nothing():
    env = make_env()
    run(env, [SELL] * 6)
    assert env.equity == pytest.approx(1.0)
    assert env.trade_count == 0


def test_fee_only_when_position_changes_and_matches_closed_form():
    env = make_env()
    run(env, [HOLD, BUY, HOLD, SELL, HOLD, HOLD])  # buy at close[2]=103, sell at close[4]=105
    assert env.equity == pytest.approx((1 - FEE) * (105 / 103) * (1 - FEE))
    assert env.trade_count == 2


def test_buy_and_hold_equals_one_round_trip():
    env = play_episode(make_env(), lambda obs: BUY)
    assert env.equity == pytest.approx((1 - FEE) ** 2 * CLOSE[7] / CLOSE[1])
    assert env.completed_trade_returns == [pytest.approx(env.equity - 1)]


def test_rewards_sum_to_log_final_equity():
    env = make_env()
    rewards = run(env, [BUY, SELL, BUY, HOLD, SELL, BUY])
    assert sum(rewards) == pytest.approx(np.log(env.equity))


def test_round_trip_returns_are_net_of_both_fees():
    env = make_env()
    # day 1 buy at 101, day 2 sell at 103; day 3 buy at 102, day 5 sell at 107
    run(env, [BUY, SELL, BUY, HOLD, SELL, HOLD])
    assert env.completed_trade_returns == [
        pytest.approx((1 - FEE) ** 2 * 103 / 101 - 1),
        pytest.approx((1 - FEE) ** 2 * 107 / 102 - 1),
    ]


def test_daily_records_cover_every_day_and_end_in_cash():
    env = play_episode(make_env(), lambda obs: BUY)
    assert [r.day_index for r in env.daily_records] == list(range(1, 8))
    assert env.daily_records[-1].equity == pytest.approx(env.equity)
    assert env.daily_records[-1].in_position is False
    assert env.in_position is False


def test_observation_has_window_and_position():
    env = make_env()
    obs, _ = env.reset()
    np.testing.assert_array_equal(obs[:-1], FEATURES[0:2].ravel())
    assert obs[-1] == 0.0
    obs, *_ = env.step(BUY)
    np.testing.assert_array_equal(obs[:-1], FEATURES[1:3].ravel())
    assert obs[-1] == 1.0


def test_observation_never_contains_future_rows():
    """Changing later days' features must not change today's observation."""
    changed_future = FEATURES.copy()
    changed_future[4:] = 999
    observations = []
    for features in (FEATURES, changed_future):
        env = make_env(features=features)
        env.reset()
        for _ in range(2):
            obs, *_ = env.step(HOLD)
        observations.append(obs)  # at day 3: rows 2..3 only
    np.testing.assert_array_equal(*observations)


def test_rejects_window_before_history():
    with pytest.raises(ValueError):
        make_env(first_day=0, last_day=5)
