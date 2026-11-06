"""Export the results and pre-generated, grounded answers as static JSON for the dashboard.

    python -m src.dashboard_snapshot                 # results + answers to the curated questions
    python -m src.dashboard_snapshot --keep-answers  # results only; reuse the answers already exported

Writes three files to DASHBOARD_DATA_DIR (web/public/data by default):
  dashboard.json         configuration, freshness, per-strategy metrics and comparisons, evals
  equity_curves.json     seed-averaged daily equity per strategy, next to buy-and-hold
  assistant_answers.json answers to questions marked show_on_dashboard in evals/assistant_questions.json

The site reads only these files: no database, API or credentials are involved.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from .assistant.assistant_evaluation import load_questions
from .assistant.request_log import save_assistant_request
from .assistant.result_queries import (CompareArguments, StrategyArguments, compare_to_baseline, data_freshness,
                                       get_equity_curve, get_metrics)
from .assistant.results_assistant import ResultsAssistant
from .database import connect_as_reader
from .settings import Settings, load_settings

_JSON = TypeAdapter(Any)


def _latest_report(reports_dir: Path, pattern: str) -> dict | None:
    reports = sorted(reports_dir.glob(pattern))
    return json.loads(reports[-1].read_text()) if reports else None


def configuration(settings: Settings) -> dict:
    return {
        "tickers": list(settings.market_data.tickers),
        "algorithms": list(settings.training.algorithms),
        "feature_sets": list(settings.training.feature_sets),
        "seeds": list(settings.training.seeds),
        "training_timesteps": settings.training.timesteps,
        "observation_window_days": settings.trading.observation_window_days,
        "buy_fee_pct": round(100 * settings.trading.buy_fee_rate, 4),
        "sell_fee_pct": round(100 * settings.trading.sell_fee_rate, 4),
        "train_start": settings.windows.train_start, "train_end": settings.windows.train_end,
        "test_start": settings.windows.test_start, "test_end": settings.windows.test_end,
        "confidence_level_pct": round(100 * settings.analysis.confidence_level, 1),
        "bootstrap_samples": settings.analysis.bootstrap_samples,
        "bootstrap_block_days": settings.analysis.bootstrap_block_days,
        "assistant_model": settings.assistant.model,
    }


def strategy_rows() -> tuple[list[dict], dict]:
    """Every strategy and period: metrics, comparison, per-seed returns, and its equity curve."""
    with connect_as_reader() as conn:
        keys = conn.execute("""SELECT ticker, algorithm, feature_set, evaluation_period FROM strategy_results
                               ORDER BY evaluation_period, ticker, algorithm, feature_set""").fetchall()
        seed_returns = conn.execute("""
            SELECT r.ticker, r.algorithm, r.feature_set, m.evaluation_period, r.seed, m.total_return
            FROM current_training_runs r JOIN run_metrics m ON m.run_id = r.id
            ORDER BY r.seed""").fetchall()
    seed_returns_by_key: dict[tuple, list[dict]] = {}
    for s in seed_returns:
        key = (s["ticker"], s["algorithm"], s["feature_set"], s["evaluation_period"])
        seed_returns_by_key.setdefault(key, []).append(
            {"seed": s["seed"], "total_return_pct": round(100 * s["total_return"], 2)})
    comparisons: dict[tuple, dict] = {}
    rows, curves = [], {}
    for key in keys:
        ticker, algorithm, feature_set, period = key.values()
        if (ticker, period) not in comparisons:
            comparisons[(ticker, period)] = {
                (c.algorithm, c.feature_set): c.model_dump(mode="json")
                for c in compare_to_baseline(CompareArguments(ticker=ticker, period=period))}
        arguments = StrategyArguments(ticker=ticker, algorithm=algorithm, feature_set=feature_set, period=period)
        rows.append({**get_metrics(arguments).model_dump(mode="json"),
                     "seed_returns": seed_returns_by_key.get((ticker, algorithm, feature_set, period), []),
                     "comparison": comparisons[(ticker, period)].get((algorithm, feature_set))})
        curve = get_equity_curve(arguments, max_points=None)
        curves.setdefault(period, {}).setdefault(ticker, {})[f"{algorithm}|{feature_set}"] = [
            [p.date.isoformat(), p.strategy_equity, p.buy_and_hold_equity] for p in curve.points]
    return rows, curves


def baseline_rows() -> list[dict]:
    with connect_as_reader() as conn:
        rows = conn.execute("""SELECT ticker, evaluation_period AS period, period_start, period_end, trading_days,
                                      total_return, sharpe_ratio, max_drawdown
                               FROM buy_and_hold_baselines ORDER BY evaluation_period, ticker""").fetchall()
    return [{**{k: r[k] for k in ("ticker", "period", "period_start", "period_end", "trading_days")},
             "total_return_pct": round(100 * r["total_return"], 2),
             "sharpe_ratio": None if r["sharpe_ratio"] is None else round(r["sharpe_ratio"], 2),
             "max_drawdown_pct": round(100 * r["max_drawdown"], 2)} for r in rows]


def period_summary(strategies: list[dict]) -> dict:
    summary = {}
    for period in sorted({s["period"] for s in strategies}):
        compared = [s["comparison"] for s in strategies if s["period"] == period and s["comparison"]]
        best = max(compared, key=lambda c: c["excess_return_pct"], default=None)
        summary[period] = {
            "strategies": len(compared),
            "beating_buy_and_hold": sum(c["beats_buy_and_hold"] for c in compared),
            "seeds": sum(c["seed_count"] for c in compared),
            "seeds_beating_buy_and_hold": sum(c["seeds_beating_buy_and_hold"] for c in compared),
            "best_by_excess_return": best,
        }
    return summary


def evaluation_summaries(settings: Settings) -> dict:
    reports_dir = settings.evaluation_reports_dir
    price = _latest_report(reports_dir, "price_data_checks_*.json")
    model_slug = settings.assistant.model.replace(":", "-").replace("/", "-")
    assistant = _latest_report(reports_dir, f"assistant_{model_slug}_*.json")
    return {
        "price_data": None if price is None else
        {"generated_at": price["generated_at"], "passed": price["passed"], "total": price["total"]},
        "assistant": None if assistant is None else
        {"generated_at": assistant["generated_at"], "model": assistant["model"], **assistant["summary"]},
    }


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def generate_answers() -> dict:
    assistant = ResultsAssistant()
    answers = []
    for question in (q for q in load_questions() if q.get("show_on_dashboard")):
        response = assistant.answer(question["question"])
        save_assistant_request(response)
        answers.append(response.model_dump(mode="json"))
        print(f"answered {question['id']}: grounded={response.grounding.passed} attempts={response.attempts}")
    return {"generated_at": _now(), "model": assistant.model, "answers": answers}


def export_snapshot(keep_answers: bool) -> None:
    settings = load_settings()
    out_dir = settings.dashboard_data_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    strategies, curves = strategy_rows()
    dashboard = {
        "generated_at": _now(),
        "configuration": configuration(settings),
        "freshness": data_freshness().model_dump(mode="json"),
        "summary": period_summary(strategies),
        "baselines": baseline_rows(),
        "strategies": strategies,
        "evaluations": evaluation_summaries(settings),
    }
    _write(out_dir / "dashboard.json", dashboard)
    _write(out_dir / "equity_curves.json", curves)
    answers_path = out_dir / "assistant_answers.json"
    if not (keep_answers and answers_path.exists()):
        _write(answers_path, generate_answers())
    print(f"Snapshot written to {out_dir}")


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(_JSON.dump_python(data, mode="json"), separators=(",", ":")))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--keep-answers", action="store_true", help="reuse the exported assistant answers")
    export_snapshot(parser.parse_args().keep_answers)


if __name__ == "__main__":
    main()
