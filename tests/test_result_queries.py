"""The assistant's tools against the real database: validation first, then rows that match plain SQL."""
import pytest

from src.assistant.result_queries import ASSISTANT_TOOLS, run_tool

try:
    from src.database import connect_as_reader
    with connect_as_reader() as _conn:
        _strategy = _conn.execute("SELECT * FROM strategy_results WHERE evaluation_period = 'test' LIMIT 1").fetchone()
except Exception:  # no .env or Postgres not running
    _strategy = None
if _strategy is None:
    pytest.skip("database or training results not available", allow_module_level=True)

STRATEGY = {"ticker": _strategy["ticker"], "algorithm": _strategy["algorithm"], "feature_set": _strategy["feature_set"]}


def test_ticker_is_case_insensitive():
    assert run_tool("get_metrics", {**STRATEGY, "ticker": STRATEGY["ticker"].lower()})["ticker"] == STRATEGY["ticker"]


def test_get_metrics_matches_the_view():
    result = run_tool("get_metrics", STRATEGY)
    assert result["mean_total_return_pct"] == round(100 * _strategy["mean_total_return"], 2)
    assert result["seed_count"] == _strategy["seed_count"]


def test_rank_by_drawdown_puts_lowest_first():
    ranked = run_tool("rank_strategies", {"metric": "max_drawdown", "ticker": STRATEGY["ticker"]})
    values = [r["value"] for r in ranked]
    assert values == sorted(values)
    with connect_as_reader() as conn:
        lowest = conn.execute("""SELECT algorithm, feature_set FROM strategy_results
                                 WHERE ticker = %s AND evaluation_period = 'test'
                                 ORDER BY mean_max_drawdown, algorithm, feature_set LIMIT 1""",
                              (STRATEGY["ticker"],)).fetchone()
    assert (ranked[0]["algorithm"], ranked[0]["feature_set"]) == (lowest["algorithm"], lowest["feature_set"])


def test_rank_by_return_puts_highest_first():
    values = [r["value"] for r in run_tool("rank_strategies", {"metric": "total_return"})]
    assert values == sorted(values, reverse=True)


def test_compare_to_baseline_rows_are_consistent():
    rows = run_tool("compare_to_baseline", {"ticker": STRATEGY["ticker"]})
    assert rows and all(r["ticker"] == STRATEGY["ticker"] for r in rows)
    for r in rows:
        assert r["excess_return_ci_low_pct"] <= r["excess_return_pct"] + 0.01
        assert r["beats_buy_and_hold"] == (r["excess_return_ci_low_pct"] > 0) or abs(r["excess_return_ci_low_pct"]) < 0.01


def test_equity_curve_is_capped_and_keeps_both_ends():
    curve = run_tool("get_equity_curve", STRATEGY)
    max_points = 30
    assert len(curve["points"]) <= max_points
    with connect_as_reader() as conn:
        first, last = conn.execute("""SELECT min(date) AS first, max(date) AS last FROM buy_and_hold_equity_curves
                                      WHERE ticker = %s AND evaluation_period = 'test'""",
                                   (STRATEGY["ticker"],)).fetchone().values()
    assert curve["points"][0]["date"] == first.isoformat() and curve["points"][-1]["date"] == last.isoformat()


def test_data_freshness_reports_latest_price_dates():
    result = run_tool("data_freshness", {})
    with connect_as_reader() as conn:
        latest = conn.execute("SELECT max(date) AS latest FROM daily_prices").fetchone()["latest"]
    assert max(t["latest_price_date"] for t in result["latest_prices"]) == latest.isoformat()


def test_list_strategies_has_every_tool_metric():
    catalog = run_tool("list_strategies", {})
    assert STRATEGY["ticker"] in catalog["tickers"]
    assert "max_drawdown" in catalog["ranking_metrics"]


def test_every_tool_has_an_ollama_definition():
    for tool in ASSISTANT_TOOLS.values():
        definition = tool.ollama_definition()
        assert definition["function"]["name"] == tool.name
        assert definition["function"]["parameters"]["type"] == "object"


def test_rank_lowest_first_reverses_the_order():
    best = run_tool("rank_strategies", {"metric": "total_return", "ticker": STRATEGY["ticker"]})
    worst = run_tool("rank_strategies", {"metric": "total_return", "ticker": STRATEGY["ticker"], "order": "lowest_first"})
    assert [r["value"] for r in worst] == sorted(r["value"] for r in best)
    assert worst[0]["order"] == "lowest_first" and worst[0]["value"] == best[-1]["value"]


def test_rank_highest_drawdown_first():
    values = [r["value"] for r in run_tool("rank_strategies", {"metric": "max_drawdown", "order": "highest_first"})]
    assert values == sorted(values, reverse=True)


def test_rank_without_ticker_covers_every_ticker():
    tickers = {r["ticker"] for r in run_tool("rank_strategies", {"metric": "total_return"})}
    assert tickers == set(run_tool("list_strategies", {})["tickers"])
