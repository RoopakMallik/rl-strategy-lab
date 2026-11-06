"""Train and test every configured agent, store the results, and compare with buy-and-hold.

    python -m src.trading.experiment_grid                       # the full grid from .env
    python -m src.trading.experiment_grid --algorithm PPO --ticker NVDA --feature-set indicators --seed 0
    python -m src.trading.experiment_grid --replace             # retrain agents that already exist

The grid is ALGORITHMS x FEATURE_SETS x TICKERS x SEEDS (3 x 2 x 3 x 5 = 90 by default).
Agents whose exact configuration is already stored are skipped, so an interrupted grid resumes
where it stopped. Each agent's run row, metrics and equity curve are committed together.
"""
from __future__ import annotations

import argparse
import itertools

import torch

from ..database import connect_as_writer
from ..experiment_options import ALGORITHMS, FEATURE_SETS
from ..market_data.price_history import MarketData, load_market_data
from ..settings import PROJECT_ROOT, Settings, load_settings
from .agent_training import evaluate_agent, evaluate_buy_and_hold, train_agent
from .results_store import (RunConfiguration, delete_training_run, find_training_run_id, insert_training_run,
                            reserve_training_run_id, save_buy_and_hold, save_run_evaluation)
from .strategy_comparison import refresh_strategy_comparisons


def model_file_name(run_id: int, config: RunConfiguration) -> str:
    return f"run{run_id}_{config.algorithm}_{config.feature_set}_{config.ticker}_seed{config.seed}.zip"


def train_and_store_agent(settings: Settings, config: RunConfiguration, market: MarketData, replace: bool) -> str:
    """Train, test and store one agent. Returns a one-line status."""
    with connect_as_writer() as conn:
        existing_id = find_training_run_id(conn, config)
        if existing_id is not None and not replace:
            return f"skip   {config.label} (run {existing_id} exists)"

        model, training_seconds = train_agent(config.algorithm, market, config.train_start, config.train_end,
                                              settings.trading, config.seed, config.training_timesteps)
        test_episode = evaluate_agent(model, market, config.test_start, config.test_end, settings.trading)
        summary = test_episode.summarize(settings.analysis.risk_free_rate)

        replaced_model = None
        with conn.transaction():
            if existing_id is not None:
                replaced_model = PROJECT_ROOT / delete_training_run(conn, existing_id)
            run_id = reserve_training_run_id(conn)
            model_path = settings.training.models_dir / model_file_name(run_id, config)
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model.save(model_path)
            insert_training_run(conn, run_id, config, training_seconds, _project_relative(model_path))
            save_run_evaluation(conn, run_id, "test", test_episode, summary)
    if replaced_model is not None:  # only once the new run is committed
        replaced_model.unlink(missing_ok=True)
    return (f"stored {config.label}: run {run_id}, test return {summary.total_return:+.1%}, "
            f"{summary.trade_count} trades, {training_seconds:.0f}s")


def store_test_baselines(settings: Settings, tickers: list[str]) -> None:
    with connect_as_writer() as conn:
        for ticker in tickers:
            market = load_market_data(ticker, "standard")  # baseline depends only on close prices
            episode = evaluate_buy_and_hold(market, settings.windows.test_start, settings.windows.test_end,
                                            settings.trading)
            summary = episode.summarize(settings.analysis.risk_free_rate)
            with conn.transaction():
                save_buy_and_hold(conn, ticker, "test", episode, summary,
                                  settings.trading.buy_fee_rate, settings.trading.sell_fee_rate)
            print(f"baseline {ticker}: buy-and-hold test return {summary.total_return:+.1%}")


def run_grid(algorithms: list[str], feature_sets: list[str], tickers: list[str], seeds: list[int],
             replace: bool) -> None:
    settings = load_settings()
    torch.set_num_threads(settings.training.torch_threads)
    store_test_baselines(settings, tickers)
    combinations = list(itertools.product(tickers, feature_sets, algorithms, seeds))
    for ticker, feature_set, group in _grouped_by_market(combinations):
        market = load_market_data(ticker, feature_set)
        for algorithm, seed in group:
            config = RunConfiguration.from_settings(settings, algorithm, feature_set, ticker, seed)
            print(train_and_store_agent(settings, config, market, replace), flush=True)
    print(f"Compared {refresh_strategy_comparisons()} strategies with buy-and-hold.")


def _grouped_by_market(combinations):
    """Group (ticker, feature_set, algorithm, seed) so each market's features load once."""
    for (ticker, feature_set), items in itertools.groupby(combinations, key=lambda c: (c[0], c[1])):
        yield ticker, feature_set, [(algorithm, seed) for _, _, algorithm, seed in items]


def _project_relative(path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--algorithm", choices=ALGORITHMS, help="only this algorithm")
    parser.add_argument("--feature-set", choices=FEATURE_SETS, help="only this feature set")
    parser.add_argument("--ticker", help="only this ticker")
    parser.add_argument("--seed", type=int, help="only this seed")
    parser.add_argument("--replace", action="store_true", help="retrain agents that are already stored")
    args = parser.parse_args()
    run_grid(
        algorithms=[args.algorithm] if args.algorithm else list(settings.training.algorithms),
        feature_sets=[args.feature_set] if args.feature_set else list(settings.training.feature_sets),
        tickers=[args.ticker.upper()] if args.ticker else list(settings.market_data.tickers),
        seeds=[args.seed] if args.seed is not None else list(settings.training.seeds),
        replace=args.replace,
    )


if __name__ == "__main__":
    main()
