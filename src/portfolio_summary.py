"""Export a compact results summary for the portfolio website's project page.

    python -m src.portfolio_summary PATH     # e.g. ../Portfolio/portfolio/data/rlStrategyLabResults.json

Writes every strategy's comparison with buy-and-hold (both periods, in percent, rounded to one
decimal), the buy-and-hold baselines, and the latest assistant evaluation summary. Re-run it after
`make refresh` or `make eval-assistant`, then rebuild the portfolio.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .database import connect_as_reader
from .settings import load_settings


def portfolio_summary() -> dict:
    settings = load_settings()
    with connect_as_reader() as conn:
        comparisons = conn.execute("""
            SELECT ticker, algorithm, feature_set, evaluation_period AS period,
                   round(100 * excess_return::numeric, 1)::float          AS excess,
                   round(100 * excess_return_ci_low::numeric, 1)::float   AS low,
                   round(100 * excess_return_ci_high::numeric, 1)::float  AS high,
                   round(100 * strategy_return::numeric, 1)::float        AS strategy,
                   seeds_beating_buy_and_hold AS seeds_beating, seed_count, beats_buy_and_hold AS beats
            FROM strategy_baseline_comparisons
            ORDER BY period DESC, ticker, algorithm, feature_set""").fetchall()
        baselines = conn.execute("""
            SELECT ticker, evaluation_period AS period, period_start::text AS start, period_end::text AS "end",
                   trading_days AS days, round(100 * total_return::numeric, 1)::float AS buy_and_hold
            FROM buy_and_hold_baselines ORDER BY period DESC, ticker""").fetchall()
    model_slug = settings.assistant.model.replace(":", "-").replace("/", "-")
    reports = sorted(settings.evaluation_reports_dir.glob(f"assistant_{model_slug}_*.json"),
                     key=lambda path: path.stat().st_mtime)
    if not comparisons or not reports:
        raise RuntimeError("Need stored comparisons and an assistant evaluation: run `make train` and "
                           "`make eval-assistant` first.")
    report = json.loads(reports[-1].read_text())
    return {"comparisons": comparisons, "baselines": baselines,
            "assistant": report["summary"], "assistant_model": report["model"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", type=Path, help="JSON file to write")
    path = parser.parse_args().path
    path.write_text(json.dumps(portfolio_summary(), indent=1) + "\n")
    print(f"Portfolio summary written to {path}")


if __name__ == "__main__":
    main()
