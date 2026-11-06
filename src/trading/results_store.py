"""Write training runs, their evaluations and the buy-and-hold baselines to Postgres (writer role).

Callers pass an open connection and wrap related writes in `with conn.transaction():`, so one
agent's run row, metrics and equity curve are saved together or not at all.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

import psycopg

from ..settings import Settings
from .agent_training import EpisodeResult
from .performance_metrics import PerformanceSummary


@dataclass(frozen=True)
class RunConfiguration:
    """Everything that defines a trained agent. Matches training_runs_configuration_unique."""
    algorithm: str
    feature_set: str
    ticker: str
    seed: int
    train_start: date
    train_end: date
    test_start: date
    test_end: date
    training_timesteps: int
    observation_window_days: int
    buy_fee_rate: float
    sell_fee_rate: float

    @classmethod
    def from_settings(cls, settings: Settings, algorithm: str, feature_set: str, ticker: str, seed: int):
        w, t = settings.windows, settings.trading
        return cls(algorithm, feature_set, ticker, seed, w.train_start, w.train_end, w.test_start, w.test_end,
                   settings.training.timesteps, t.observation_window_days, t.buy_fee_rate, t.sell_fee_rate)

    @property
    def label(self) -> str:
        return f"{self.algorithm} / {self.feature_set} / {self.ticker} / seed {self.seed}"


_CONFIGURATION_COLUMNS = list(RunConfiguration.__dataclass_fields__)


def find_training_run_id(conn: psycopg.Connection, config: RunConfiguration) -> int | None:
    where = " AND ".join(f"{column} = %({column})s" for column in _CONFIGURATION_COLUMNS)
    row = conn.execute(f"SELECT id FROM training_runs WHERE {where}", asdict(config)).fetchone()
    return row["id"] if row else None


def reserve_training_run_id(conn: psycopg.Connection) -> int:
    """The id the next run will get, so the model file can be named after it before the insert."""
    return conn.execute("SELECT nextval(pg_get_serial_sequence('training_runs', 'id')) AS id").fetchone()["id"]


def insert_training_run(conn: psycopg.Connection, run_id: int, config: RunConfiguration,
                        training_seconds: float, model_path: str) -> None:
    columns = ["id", *_CONFIGURATION_COLUMNS, "training_seconds", "model_path"]
    values = {"id": run_id, **asdict(config), "training_seconds": training_seconds, "model_path": model_path}
    placeholders = ", ".join(f"%({column})s" for column in columns)
    conn.execute(f"INSERT INTO training_runs ({', '.join(columns)}) VALUES ({placeholders})", values)


def delete_training_run(conn: psycopg.Connection, run_id: int) -> str:
    """Deletes the run with its metrics and equity curves. Returns its model path."""
    return conn.execute("DELETE FROM training_runs WHERE id = %s RETURNING model_path", (run_id,)).fetchone()["model_path"]


def load_current_training_runs(conn: psycopg.Connection) -> list[dict]:
    return conn.execute("SELECT * FROM current_training_runs ORDER BY ticker, algorithm, feature_set, seed").fetchall()


def save_run_evaluation(conn: psycopg.Connection, run_id: int, evaluation_period: str,
                        episode: EpisodeResult, summary: PerformanceSummary) -> None:
    """Insert or replace the metrics and equity curve of one run for one period."""
    conn.execute(
        """INSERT INTO run_metrics (run_id, evaluation_period, period_start, period_end, trading_days,
               total_return, sharpe_ratio, max_drawdown, trade_count, round_trip_count, win_rate, exposure)
           VALUES (%(run_id)s, %(evaluation_period)s, %(period_start)s, %(period_end)s, %(trading_days)s,
               %(total_return)s, %(sharpe_ratio)s, %(max_drawdown)s, %(trade_count)s, %(round_trip_count)s,
               %(win_rate)s, %(exposure)s)
           ON CONFLICT (run_id, evaluation_period) DO UPDATE SET
               period_start = EXCLUDED.period_start, period_end = EXCLUDED.period_end,
               trading_days = EXCLUDED.trading_days, total_return = EXCLUDED.total_return,
               sharpe_ratio = EXCLUDED.sharpe_ratio, max_drawdown = EXCLUDED.max_drawdown,
               trade_count = EXCLUDED.trade_count, round_trip_count = EXCLUDED.round_trip_count,
               win_rate = EXCLUDED.win_rate, exposure = EXCLUDED.exposure, evaluated_at = now()""",
        {"run_id": run_id, "evaluation_period": evaluation_period, "period_start": episode.period_start,
         "period_end": episode.period_end, **asdict(summary)},
    )
    conn.execute("DELETE FROM run_equity_curves WHERE run_id = %s AND evaluation_period = %s",
                 (run_id, evaluation_period))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO run_equity_curves (run_id, evaluation_period, date, equity, in_position) VALUES (%s, %s, %s, %s, %s)",
            [(run_id, evaluation_period, d, float(e), p)
             for d, e, p in zip(episode.dates, episode.equity, episode.in_position)],
        )


def save_buy_and_hold(conn: psycopg.Connection, ticker: str, evaluation_period: str, episode: EpisodeResult,
                      summary: PerformanceSummary, buy_fee_rate: float, sell_fee_rate: float) -> None:
    """Insert or replace one ticker's buy-and-hold baseline and equity curve for one period."""
    conn.execute(
        """INSERT INTO buy_and_hold_baselines (ticker, evaluation_period, period_start, period_end, trading_days,
               buy_fee_rate, sell_fee_rate, total_return, sharpe_ratio, max_drawdown)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (ticker, evaluation_period) DO UPDATE SET
               period_start = EXCLUDED.period_start, period_end = EXCLUDED.period_end,
               trading_days = EXCLUDED.trading_days, buy_fee_rate = EXCLUDED.buy_fee_rate,
               sell_fee_rate = EXCLUDED.sell_fee_rate, total_return = EXCLUDED.total_return,
               sharpe_ratio = EXCLUDED.sharpe_ratio, max_drawdown = EXCLUDED.max_drawdown, evaluated_at = now()""",
        (ticker, evaluation_period, episode.period_start, episode.period_end, summary.trading_days,
         buy_fee_rate, sell_fee_rate, summary.total_return, summary.sharpe_ratio, summary.max_drawdown),
    )
    conn.execute("DELETE FROM buy_and_hold_equity_curves WHERE ticker = %s AND evaluation_period = %s",
                 (ticker, evaluation_period))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO buy_and_hold_equity_curves (ticker, evaluation_period, date, equity) VALUES (%s, %s, %s, %s)",
            [(ticker, evaluation_period, d, float(e)) for d, e in zip(episode.dates, episode.equity)],
        )
