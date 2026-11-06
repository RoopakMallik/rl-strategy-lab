"""Forward test: run every current trained agent on the trading days after its TEST_END.

    python -m src.trading.forward_test

These are days the agent never saw in training or testing, so this is "performance since
training", not retraining. Run it after `make refresh` downloads new prices. The first forward
windows are only a few days long: treat them as small samples.
"""
from __future__ import annotations

from datetime import date

import torch

from ..database import connect_as_writer
from ..market_data.price_history import MarketData, load_market_data
from ..settings import PROJECT_ROOT, TradingSettings, load_settings
from .agent_training import evaluate_buy_and_hold, evaluate_agent, load_agent
from .results_store import load_current_training_runs, save_buy_and_hold, save_run_evaluation
from .strategy_comparison import refresh_strategy_comparisons

# Metrics need at least two days. The buy-and-hold comparison needs more and skips shorter periods
# (see strategy_comparison.MINIMUM_BLOCKS).
MINIMUM_FORWARD_TRADING_DAYS = 2


def forward_window(test_end: date, market: MarketData) -> tuple[date, date] | None:
    """First and last trading day after `test_end`, or None if there are too few yet."""
    later_days = [d for d in market.dates if d > test_end]
    if len(later_days) < MINIMUM_FORWARD_TRADING_DAYS:
        return None
    return later_days[0], later_days[-1]


def run_forward_test() -> None:
    settings = load_settings()
    torch.set_num_threads(settings.training.torch_threads)
    markets: dict[tuple[str, str], MarketData] = {}
    baselines_done: set[tuple[str, date]] = set()
    evaluated = 0
    with connect_as_writer() as conn:
        runs = load_current_training_runs(conn)
        if not runs:
            print("No trained agents yet. Run `make train` first.")
            return
        for run in runs:
            key = (run["ticker"], run["feature_set"])
            if key not in markets:
                markets[key] = load_market_data(*key)
            market = markets[key]
            window = forward_window(run["test_end"], market)
            if window is None:
                print(f"{run['ticker']}: fewer than {MINIMUM_FORWARD_TRADING_DAYS} trading days after "
                      f"{run['test_end']}; run `make refresh` later")
                continue
            # Forward days use the same fees and window as the run was trained with.
            trading = TradingSettings(buy_fee_rate=run["buy_fee_rate"], sell_fee_rate=run["sell_fee_rate"],
                                      observation_window_days=run["observation_window_days"])
            model = load_agent(run["algorithm"], PROJECT_ROOT / run["model_path"])
            episode = evaluate_agent(model, market, window[0], window[1], trading)
            with conn.transaction():
                save_run_evaluation(conn, run["id"], "forward", episode,
                                    episode.summarize(settings.analysis.risk_free_rate))
                if (run["ticker"], run["test_end"]) not in baselines_done:
                    baseline = evaluate_buy_and_hold(market, window[0], window[1], trading)
                    save_buy_and_hold(conn, run["ticker"], "forward", baseline,
                                      baseline.summarize(settings.analysis.risk_free_rate),
                                      trading.buy_fee_rate, trading.sell_fee_rate)
                    baselines_done.add((run["ticker"], run["test_end"]))
            evaluated += 1
    print(f"Forward-tested {evaluated} of {len(runs)} agents.")
    print(f"Compared {refresh_strategy_comparisons()} strategies with buy-and-hold.")


def main() -> None:
    run_forward_test()


if __name__ == "__main__":
    main()
