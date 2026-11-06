"""Compare each strategy (all seeds together) with buy-and-hold and store the result.

    python -m src.trading.strategy_comparison

A strategy is one ticker + algorithm + feature set. Its seeds are treated as an equal-weight
portfolio: the mean of their equity curves. excess_return = (1 + strategy return) /
(1 + buy-and-hold return) - 1, i.e. how much more money the strategy ended with.

The confidence interval is a moving-block bootstrap over the period's trading days of
(strategy daily log return - buy-and-hold daily log return). A strategy "beats buy-and-hold"
only if the whole interval is above zero. The interval covers day-to-day market noise; the
spread across seeds is reported separately (seeds_beating_buy_and_hold and strategy_results).

A strategy is skipped (with a message) when its seeds were evaluated on different days, when its
days differ from the stored baseline's (e.g. TEST_END changed and only some agents were
retrained), or when the period has fewer than MINIMUM_BLOCKS bootstrap blocks of days: below that,
the bootstrap has too few distinct resamples for its interval to mean anything.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from ..database import connect_as_writer
from ..settings import AnalysisSettings, load_settings
from .performance_metrics import block_bootstrap_interval

MINIMUM_BLOCKS = 3


@dataclass(frozen=True)
class BaselineComparison:
    strategy_return: float
    buy_and_hold_return: float
    excess_return: float
    excess_return_ci_low: float
    excess_return_ci_high: float
    confidence_level: float
    seed_count: int
    seeds_beating_buy_and_hold: int
    beats_buy_and_hold: bool


def compare_with_buy_and_hold(seed_equity: pd.DataFrame, buy_and_hold_equity: pd.Series,
                              analysis: AnalysisSettings) -> BaselineComparison:
    """`seed_equity`: one column per seed, indexed by date. `buy_and_hold_equity`: same dates.

    Raises ValueError (with the reason) when the curves cannot be compared fairly.
    """
    if seed_equity.isna().any().any():
        raise ValueError("its seeds were evaluated on different days; retrain them with --replace")
    if not seed_equity.index.equals(buy_and_hold_equity.index):
        raise ValueError("its days differ from the stored buy-and-hold baseline's; retrain or re-run the forward test")
    minimum_days = MINIMUM_BLOCKS * analysis.bootstrap_block_days + 1
    if len(seed_equity) < minimum_days:
        raise ValueError(f"only {len(seed_equity)} trading days; at least {minimum_days} are needed "
                         f"for a confidence interval")
    mean_equity = seed_equity.mean(axis=1).to_numpy()
    baseline = buy_and_hold_equity.to_numpy()
    daily_log_difference = np.diff(np.log(mean_equity)) - np.diff(np.log(baseline))
    ci_low, ci_high = block_bootstrap_interval(
        daily_log_difference, analysis.confidence_level, analysis.bootstrap_samples,
        analysis.bootstrap_block_days, analysis.bootstrap_random_seed)
    seed_finals = seed_equity.iloc[-1] / seed_equity.iloc[0]
    baseline_final = baseline[-1] / baseline[0]
    return BaselineComparison(
        strategy_return=float(mean_equity[-1] / mean_equity[0] - 1),
        buy_and_hold_return=float(baseline_final - 1),
        excess_return=float(np.expm1(daily_log_difference.sum())),
        excess_return_ci_low=float(np.expm1(ci_low)),
        excess_return_ci_high=float(np.expm1(ci_high)),
        confidence_level=analysis.confidence_level,
        seed_count=seed_equity.shape[1],
        seeds_beating_buy_and_hold=int((seed_finals > baseline_final).sum()),
        beats_buy_and_hold=bool(ci_low > 0),
    )


def refresh_strategy_comparisons() -> int:
    """Recompute every strategy's comparison from the stored equity curves. Returns the row count."""
    analysis = load_settings().analysis
    with connect_as_writer() as conn:
        strategy_curves = pd.DataFrame(conn.execute(
            """SELECT r.ticker, r.algorithm, r.feature_set, c.evaluation_period, r.seed, c.date, c.equity
               FROM current_training_runs r JOIN run_equity_curves c ON c.run_id = r.id""").fetchall())
        baseline_curves = pd.DataFrame(conn.execute(
            "SELECT ticker, evaluation_period, date, equity FROM buy_and_hold_equity_curves").fetchall())
        if strategy_curves.empty or baseline_curves.empty:
            print("No equity curves stored yet; nothing to compare.")
            return 0

        rows = []
        strategy_keys = ["ticker", "algorithm", "feature_set", "evaluation_period"]
        for (ticker, algorithm, feature_set, period), curves in strategy_curves.groupby(strategy_keys):
            seed_equity = curves.pivot(index="date", columns="seed", values="equity").sort_index()
            baseline = (baseline_curves[(baseline_curves["ticker"] == ticker) &
                                        (baseline_curves["evaluation_period"] == period)]
                        .set_index("date")["equity"].sort_index())
            if baseline.empty:
                print(f"Skipping {ticker} {period}: no buy-and-hold baseline stored")
                continue
            try:
                comparison = compare_with_buy_and_hold(seed_equity, baseline, analysis)
            except ValueError as reason:
                print(f"Skipping {algorithm} / {feature_set} / {ticker} ({period}): {reason}")
                continue
            rows.append({"ticker": ticker, "algorithm": algorithm, "feature_set": feature_set,
                         "evaluation_period": period, "period_start": seed_equity.index[0],
                         "period_end": seed_equity.index[-1], **asdict(comparison)})

        columns = list(rows[0]) if rows else []
        with conn.transaction():
            conn.execute("DELETE FROM strategy_baseline_comparisons")
            if rows:
                with conn.cursor() as cur:
                    cur.executemany(
                        f"INSERT INTO strategy_baseline_comparisons ({', '.join(columns)}) "
                        f"VALUES ({', '.join(f'%({c})s' for c in columns)})", rows)
    return len(rows)


def main() -> None:
    print(f"Stored {refresh_strategy_comparisons()} strategy comparisons with buy-and-hold.")


if __name__ == "__main__":
    main()
