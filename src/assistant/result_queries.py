"""The six fixed queries the assistant (and the API) may run. Read-only role, parameterized SQL.

Qwen never writes SQL: it picks a tool by name and passes arguments, which are validated against
the Pydantic models below before any query runs. Results are compact and already rounded, with
returns and rates given in PERCENT (fields ending in _pct), so the model can quote them as-is.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable, Literal

import psycopg
from psycopg import sql
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator

from ..database import connect_as_reader
from ..experiment_options import ALGORITHMS, EVALUATION_PERIODS, FEATURE_SETS
from ..settings import load_settings

Algorithm = Literal[ALGORITHMS]
FeatureSet = Literal[FEATURE_SETS]
EvaluationPeriod = Literal[EVALUATION_PERIODS]
RankingMetric = Literal["total_return", "sharpe_ratio", "max_drawdown", "win_rate", "excess_return"]
RankingOrder = Literal["highest_first", "lowest_first"]

PERCENT_DECIMALS = 2
RATIO_DECIMALS = 2
EQUITY_DECIMALS = 4


class ToolArgumentError(ValueError):
    """The arguments failed validation. The message is safe to show to the model or a user."""


class NoResultsError(LookupError):
    """The arguments were valid but nothing is stored for them (e.g. not trained yet)."""


class ToolExecutionError(RuntimeError):
    """The query failed in the database. The message names the tool, not the SQL."""


def _percent(fraction: float | None) -> float | None:
    return None if fraction is None else round(100 * float(fraction), PERCENT_DECIMALS)


def _rounded(value: float | None, decimals: int) -> float | None:
    return None if value is None else round(float(value), decimals)


# --- Arguments --------------------------------------------------------------------------------

class _Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _TickerArgument(_Arguments):
    @field_validator("ticker", mode="before", check_fields=False)
    @classmethod
    def _known_ticker(cls, value):
        if value is None:
            return None
        ticker = str(value).strip().upper()
        known = load_settings().market_data.tickers
        if ticker not in known:
            raise ValueError(f"unknown ticker {ticker!r}; available: {', '.join(known)}")
        return ticker


class NoArguments(_Arguments):
    pass


class StrategyArguments(_TickerArgument):
    ticker: str = Field(description="Stock ticker, e.g. NVDA")
    algorithm: Algorithm
    feature_set: FeatureSet = Field(description="'standard' (price and volume) or 'indicators' (adds SMA, RSI, OBV)")
    period: EvaluationPeriod = Field("test", description="'test' (held-out year) or 'forward' (days since)")


class CompareArguments(_TickerArgument):
    ticker: str = Field(description="Stock ticker, e.g. NVDA")
    algorithm: Algorithm | None = Field(None, description="Leave out to include every algorithm")
    feature_set: FeatureSet | None = Field(None, description="Leave out to include both feature sets")
    period: EvaluationPeriod = "test"


class RankArguments(_TickerArgument):
    metric: RankingMetric
    order: RankingOrder | None = Field(None, description="Sort by the value itself: 'highest_first' or "
                                       "'lowest_first' (e.g. lowest_first for the worst return or the lowest "
                                       "drawdown). Leave out to rank best first.")
    ticker: str | None = Field(None, description="Set ONLY if the question names one ticker. Leave out for "
                               "questions about all tickers, overall, or across tickers.")
    period: EvaluationPeriod = "test"


# --- Results ----------------------------------------------------------------------------------

class StrategyCatalog(BaseModel):
    tickers: list[str]
    algorithms: list[str]
    feature_sets: list[str]
    periods_with_results: list[str]
    ranking_metrics: list[str]
    seeds_per_strategy: int | None
    buy_fee_pct: list[float]          # as stored with the trained agents
    sell_fee_pct: list[float]
    training_timesteps: list[int]


class StrategyMetrics(BaseModel):
    ticker: str
    algorithm: str
    feature_set: str
    period: str
    period_start: date
    period_end: date
    seed_count: int
    mean_total_return_pct: float
    stddev_total_return_pct: float | None
    min_total_return_pct: float
    max_total_return_pct: float
    mean_sharpe_ratio: float | None
    mean_max_drawdown_pct: float
    mean_trade_count: float
    mean_win_rate_pct: float | None
    mean_exposure_pct: float
    buy_and_hold_return_pct: float | None


class BaselineComparison(BaseModel):
    ticker: str
    algorithm: str
    feature_set: str
    period: str
    period_start: date
    period_end: date
    strategy_return_pct: float
    buy_and_hold_return_pct: float
    excess_return_pct: float
    excess_return_ci_low_pct: float
    excess_return_ci_high_pct: float
    confidence_level_pct: float
    seed_count: int
    seeds_beating_buy_and_hold: int
    beats_buy_and_hold: bool


class RankedStrategy(BaseModel):
    rank: int
    ticker: str
    algorithm: str
    feature_set: str
    period: str
    order: str
    metric: str
    value: float | None


class EquityPoint(BaseModel):
    date: date
    strategy_equity: float
    buy_and_hold_equity: float | None


class EquityCurve(BaseModel):
    ticker: str
    algorithm: str
    feature_set: str
    period: str
    note: str
    points: list[EquityPoint]


class TrainingWindow(BaseModel):
    train_start: date
    train_end: date
    test_start: date
    test_end: date
    agents: int
    last_trained_at: datetime


class TickerFreshness(BaseModel):
    ticker: str
    latest_price_date: date


class DataFreshness(BaseModel):
    latest_prices: list[TickerFreshness]
    last_price_refresh_at: datetime | None
    training_windows: list[TrainingWindow]
    forward_period_end: date | None


# --- Queries ----------------------------------------------------------------------------------

def list_strategies(_: NoArguments | None = None) -> StrategyCatalog:
    with connect_as_reader() as conn:
        row = conn.execute("""
            SELECT array_agg(DISTINCT ticker ORDER BY ticker)               AS tickers,
                   array_agg(DISTINCT algorithm ORDER BY algorithm)         AS algorithms,
                   array_agg(DISTINCT feature_set ORDER BY feature_set)     AS feature_sets,
                   array_agg(DISTINCT evaluation_period ORDER BY evaluation_period) AS periods,
                   max(seed_count)                                          AS seeds
            FROM strategy_results""").fetchone()
        run_settings = conn.execute("""
            SELECT array_agg(DISTINCT buy_fee_rate)       AS buy_fees,
                   array_agg(DISTINCT sell_fee_rate)      AS sell_fees,
                   array_agg(DISTINCT training_timesteps) AS timesteps
            FROM current_training_runs""").fetchone()
    if not row["tickers"]:
        raise NoResultsError("No results are stored yet. Run `make train`.")
    return StrategyCatalog(tickers=row["tickers"], algorithms=row["algorithms"], feature_sets=row["feature_sets"],
                           periods_with_results=row["periods"], ranking_metrics=list(RankingMetric.__args__),
                           seeds_per_strategy=row["seeds"],
                           buy_fee_pct=sorted(_percent(f) for f in run_settings["buy_fees"]),
                           sell_fee_pct=sorted(_percent(f) for f in run_settings["sell_fees"]),
                           training_timesteps=sorted(run_settings["timesteps"]))


def get_metrics(args: StrategyArguments) -> StrategyMetrics:
    with connect_as_reader() as conn:
        row = conn.execute("""
            SELECT s.*, b.total_return AS buy_and_hold_return
            FROM strategy_results s
            LEFT JOIN buy_and_hold_baselines b
              ON b.ticker = s.ticker AND b.evaluation_period = s.evaluation_period
            WHERE s.ticker = %s AND s.algorithm = %s AND s.feature_set = %s AND s.evaluation_period = %s""",
            (args.ticker, args.algorithm, args.feature_set, args.period)).fetchone()
    if row is None:
        raise NoResultsError(f"No {args.period} results for {args.algorithm} / {args.feature_set} / {args.ticker}.")
    return StrategyMetrics(
        ticker=row["ticker"], algorithm=row["algorithm"], feature_set=row["feature_set"], period=row["evaluation_period"],
        period_start=row["period_start"], period_end=row["period_end"], seed_count=row["seed_count"],
        mean_total_return_pct=_percent(row["mean_total_return"]),
        stddev_total_return_pct=_percent(row["stddev_total_return"]),
        min_total_return_pct=_percent(row["min_total_return"]),
        max_total_return_pct=_percent(row["max_total_return"]),
        mean_sharpe_ratio=_rounded(row["mean_sharpe_ratio"], RATIO_DECIMALS),
        mean_max_drawdown_pct=_percent(row["mean_max_drawdown"]),
        mean_trade_count=_rounded(row["mean_trade_count"], 1),
        mean_win_rate_pct=_percent(row["mean_win_rate"]),
        mean_exposure_pct=_percent(row["mean_exposure"]),
        buy_and_hold_return_pct=_percent(row["buy_and_hold_return"]),
    )


def compare_to_baseline(args: CompareArguments) -> list[BaselineComparison]:
    with connect_as_reader() as conn:
        rows = conn.execute("""
            SELECT * FROM strategy_baseline_comparisons
            WHERE ticker = %(ticker)s AND evaluation_period = %(period)s
              AND (%(algorithm)s::text IS NULL OR algorithm = %(algorithm)s)
              AND (%(feature_set)s::text IS NULL OR feature_set = %(feature_set)s)
            ORDER BY excess_return DESC""", args.model_dump()).fetchall()
    if not rows:
        raise NoResultsError(f"No {args.period} comparison stored for {args.ticker}.")
    return [BaselineComparison(
        ticker=r["ticker"], algorithm=r["algorithm"], feature_set=r["feature_set"], period=r["evaluation_period"],
        period_start=r["period_start"], period_end=r["period_end"],
        strategy_return_pct=_percent(r["strategy_return"]),
        buy_and_hold_return_pct=_percent(r["buy_and_hold_return"]),
        excess_return_pct=_percent(r["excess_return"]),
        excess_return_ci_low_pct=_percent(r["excess_return_ci_low"]),
        excess_return_ci_high_pct=_percent(r["excess_return_ci_high"]),
        confidence_level_pct=_percent(r["confidence_level"]),
        seed_count=r["seed_count"], seeds_beating_buy_and_hold=r["seeds_beating_buy_and_hold"],
        beats_buy_and_hold=r["beats_buy_and_hold"],
    ) for r in rows]


# metric -> (column in the ranking query, best-first sort direction, name of the value in the result, as percent?)
_ORDER_NAMES = {"DESC": "highest_first", "ASC": "lowest_first"}
_RANKING_COLUMNS = {
    "total_return": ("mean_total_return", "DESC", "mean_total_return_pct", True),
    "sharpe_ratio": ("mean_sharpe_ratio", "DESC", "mean_sharpe_ratio", False),
    "max_drawdown": ("mean_max_drawdown", "ASC", "mean_max_drawdown_pct", True),
    "win_rate": ("mean_win_rate", "DESC", "mean_win_rate_pct", True),
    "excess_return": ("excess_return", "DESC", "excess_return_pct", True),
}


def rank_strategies(args: RankArguments) -> list[RankedStrategy]:
    column, best_first, value_name, as_percent = _RANKING_COLUMNS[args.metric]
    direction = {"highest_first": "DESC", "lowest_first": "ASC", None: best_first}[args.order]
    query = sql.SQL("""
        SELECT s.ticker, s.algorithm, s.feature_set, s.evaluation_period, {column} AS value
        FROM strategy_results s
        LEFT JOIN strategy_baseline_comparisons c USING (ticker, algorithm, feature_set, evaluation_period)
        WHERE s.evaluation_period = %(period)s AND (%(ticker)s::text IS NULL OR s.ticker = %(ticker)s)
        ORDER BY value {direction} NULLS LAST, s.ticker, s.algorithm, s.feature_set""").format(
        column=sql.Identifier(column), direction=sql.SQL(direction))
    with connect_as_reader() as conn:
        rows = conn.execute(query, args.model_dump()).fetchall()
    if not rows:
        raise NoResultsError(f"No {args.period} results to rank.")
    return [RankedStrategy(rank=i, ticker=r["ticker"], algorithm=r["algorithm"], feature_set=r["feature_set"],
                           period=r["evaluation_period"], order=_ORDER_NAMES[direction], metric=value_name,
                           value=_percent(r["value"]) if as_percent else _rounded(r["value"], RATIO_DECIMALS))
            for i, r in enumerate(rows, start=1)]


def get_equity_curve(args: StrategyArguments, max_points: int | None = None) -> EquityCurve:
    """Seed-averaged equity (starts at 1.0) next to buy-and-hold. `max_points=None` returns every day."""
    with connect_as_reader() as conn:
        rows = conn.execute("""
            SELECT c.date, avg(c.equity) AS strategy_equity, max(b.equity) AS buy_and_hold_equity
            FROM current_training_runs r
            JOIN run_equity_curves c ON c.run_id = r.id
            LEFT JOIN buy_and_hold_equity_curves b
              ON b.ticker = r.ticker AND b.evaluation_period = c.evaluation_period AND b.date = c.date
            WHERE r.ticker = %s AND r.algorithm = %s AND r.feature_set = %s AND c.evaluation_period = %s
            GROUP BY c.date ORDER BY c.date""",
            (args.ticker, args.algorithm, args.feature_set, args.period)).fetchall()
    if not rows:
        raise NoResultsError(f"No {args.period} equity curve for {args.algorithm} / {args.feature_set} / {args.ticker}.")
    sampled = _evenly_spaced(rows, max_points)
    note = "Equity starts at 1.0. Mean across seeds."
    if len(sampled) < len(rows):
        note += f" Showing {len(sampled)} of {len(rows)} trading days, evenly spaced, first and last included."
    return EquityCurve(ticker=args.ticker, algorithm=args.algorithm, feature_set=args.feature_set,
                       period=args.period, note=note,
                       points=[EquityPoint(date=r["date"], strategy_equity=_rounded(r["strategy_equity"], EQUITY_DECIMALS),
                                           buy_and_hold_equity=_rounded(r["buy_and_hold_equity"], EQUITY_DECIMALS))
                               for r in sampled])


def _evenly_spaced(rows: list, max_points: int | None) -> list:
    if max_points is None or len(rows) <= max_points:
        return rows
    last = len(rows) - 1
    indexes = sorted({round(i * last / (max_points - 1)) for i in range(max_points)})
    return [rows[i] for i in indexes]


def data_freshness(_: NoArguments | None = None) -> DataFreshness:
    with connect_as_reader() as conn:
        latest_prices = conn.execute(
            "SELECT ticker, max(date) AS latest_price_date FROM daily_prices GROUP BY ticker ORDER BY ticker").fetchall()
        last_refresh = conn.execute("SELECT max(ingested_at) AS at FROM price_ingest_log").fetchone()["at"]
        windows = conn.execute("""
            SELECT train_start, train_end, test_start, test_end, count(*) AS agents, max(created_at) AS last_trained_at
            FROM current_training_runs GROUP BY 1, 2, 3, 4 ORDER BY train_end""").fetchall()
        forward_end = conn.execute(
            "SELECT max(period_end) AS period_end FROM run_metrics WHERE evaluation_period = 'forward'").fetchone()
    return DataFreshness(latest_prices=[TickerFreshness(**r) for r in latest_prices],
                         last_price_refresh_at=last_refresh,
                         training_windows=[TrainingWindow(**w) for w in windows],
                         forward_period_end=forward_end["period_end"])


# --- Registry ---------------------------------------------------------------------------------

@dataclass(frozen=True)
class AssistantTool:
    name: str
    description: str
    arguments: type[_Arguments]
    run: Callable[[Any], Any]

    def ollama_definition(self) -> dict:
        """The tool as Ollama's chat API expects it, with the configured tickers as an enum."""
        parameters = self.arguments.model_json_schema()
        parameters.pop("title", None)
        for name, schema in parameters.get("properties", {}).items():
            schema.pop("title", None)
            if name == "ticker":
                schema["enum"] = list(load_settings().market_data.tickers)
                schema.pop("anyOf", None)
                schema["type"] = "string"
        parameters.setdefault("properties", {})
        return {"type": "function",
                "function": {"name": self.name, "description": self.description, "parameters": parameters}}


ASSISTANT_TOOLS: dict[str, AssistantTool] = {tool.name: tool for tool in [
    AssistantTool("list_strategies",
                  "List the tickers, algorithms, feature sets and evaluation periods that have stored results, "
                  "plus the trading fees and training timesteps the agents used.",
                  NoArguments, list_strategies),
    AssistantTool("get_metrics",
                  "Mean and spread across seeds of return, Sharpe ratio, max drawdown, trade count, win rate and "
                  "exposure for ONE strategy (ticker + algorithm + feature set), plus buy-and-hold's return.",
                  StrategyArguments, get_metrics),
    AssistantTool("compare_to_baseline",
                  "Compare strategies on one ticker with buy-and-hold: strategy return, buy-and-hold return, "
                  "excess return with its confidence interval, and whether it beats buy-and-hold.",
                  CompareArguments, compare_to_baseline),
    AssistantTool("rank_strategies",
                  "Rank strategies by one metric (total_return, sharpe_ratio, max_drawdown, win_rate or "
                  "excess_return). Best first by default (smallest drawdown, highest of the others), or "
                  "highest_first / lowest_first. Rank 1 answers the question. Covers all tickers unless one "
                  "is given.",
                  RankArguments, rank_strategies),
    AssistantTool("get_equity_curve",
                  "Dates and seed-averaged equity of one strategy next to buy-and-hold's equity.",
                  StrategyArguments,
                  lambda args: get_equity_curve(args, load_settings().assistant.equity_curve_max_points)),
    AssistantTool("data_freshness",
                  "Latest stored price date per ticker, when prices were last refreshed, the training and test "
                  "windows of the trained agents, and the end of the forward period.",
                  NoArguments, data_freshness),
]}


def run_tool(name: str, raw_arguments: dict | None) -> Any:
    """Validate the arguments, run the query and return JSON-ready data.

    Raises ToolArgumentError for an unknown tool or bad arguments, NoResultsError if nothing is
    stored, and ToolExecutionError if the database query fails.
    """
    tool = ASSISTANT_TOOLS.get(name)
    if tool is None:
        raise ToolArgumentError(f"unknown tool {name!r}; available: {', '.join(ASSISTANT_TOOLS)}")
    try:
        arguments = tool.arguments.model_validate(raw_arguments or {})
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'arguments'}: {e['msg']}" for e in exc.errors())
        raise ToolArgumentError(f"invalid arguments for {name}: {problems}") from None
    try:
        result = tool.run(arguments)
    except psycopg.Error as exc:
        raise ToolExecutionError(f"{name} failed in the database: {exc.__class__.__name__}") from exc
    return _JSON.dump_python(result, mode="json")


_JSON = TypeAdapter(Any)
