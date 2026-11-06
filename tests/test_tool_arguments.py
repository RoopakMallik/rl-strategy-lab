"""Tool arguments are validated before any query runs, so these need no database."""
import pytest

from src.assistant.result_queries import RankArguments, StrategyArguments, ToolArgumentError, run_tool

STRATEGY = {"ticker": "NVDA", "algorithm": "PPO", "feature_set": "indicators"}


@pytest.mark.parametrize("name, arguments, message", [
    ("get_metrics", {**STRATEGY, "ticker": "TSLA"}, "unknown ticker"),
    ("get_metrics", {**STRATEGY, "algorithm": "SAC"}, "algorithm"),
    ("get_metrics", {**STRATEGY, "period": "2019"}, "period"),
    ("get_metrics", {"ticker": "NVDA"}, "algorithm"),
    ("rank_strategies", {"metric": "profit"}, "metric"),
    ("rank_strategies", {"metric": "total_return", "order": "random"}, "order"),
    ("get_metrics", {**STRATEGY, "sql": "DROP TABLE daily_prices"}, "sql"),
    ("drop_everything", {}, "unknown tool"),
])
def test_bad_arguments_are_rejected_before_any_query(name, arguments, message):
    with pytest.raises(ToolArgumentError, match=message):
        run_tool(name, arguments)


def test_ticker_is_normalised_to_upper_case():
    assert StrategyArguments.model_validate({**STRATEGY, "ticker": " nvda "}).ticker == "NVDA"


def test_ranking_defaults_to_best_first_across_all_tickers():
    arguments = RankArguments.model_validate({"metric": "total_return"})
    assert arguments.ticker is None and arguments.order is None and arguments.period == "test"
