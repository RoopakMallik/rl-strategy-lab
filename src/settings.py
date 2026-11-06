"""All settings, loaded once from .env. No other module reads environment variables.

Settings are grouped by the part of the system that uses them. `.env.example` documents each one.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from psycopg.conninfo import make_conninfo

from .experiment_options import ALGORITHMS, FEATURE_SETS

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class DatabaseSettings:
    host: str
    port: int
    name: str
    writer_user: str
    writer_password: str
    reader_user: str
    reader_password: str

    @property
    def writer_conninfo(self) -> str:
        """Writer role: ingest, training, migrations and request logging."""
        return make_conninfo(host=self.host, port=self.port, dbname=self.name,
                             user=self.writer_user, password=self.writer_password)

    @property
    def reader_conninfo(self) -> str:
        """Read-only role: assistant tools, API and analysis."""
        return make_conninfo(host=self.host, port=self.port, dbname=self.name,
                             user=self.reader_user, password=self.reader_password)


@dataclass(frozen=True)
class MarketDataSettings:
    tickers: tuple[str, ...]
    history_start: date
    history_end: date | None  # None means "up to today"


@dataclass(frozen=True)
class EvaluationWindowSettings:
    train_start: date
    train_end: date
    test_start: date
    test_end: date


@dataclass(frozen=True)
class TradingSettings:
    buy_fee_rate: float
    sell_fee_rate: float
    observation_window_days: int


@dataclass(frozen=True)
class TrainingSettings:
    algorithms: tuple[str, ...]
    feature_sets: tuple[str, ...]
    seeds: tuple[int, ...]
    timesteps: int
    torch_threads: int
    models_dir: Path


@dataclass(frozen=True)
class AnalysisSettings:
    risk_free_rate: float
    confidence_level: float
    bootstrap_samples: int
    bootstrap_block_days: int
    bootstrap_random_seed: int


@dataclass(frozen=True)
class AssistantSettings:
    ollama_host: str
    model: str
    temperature: float
    max_tool_rounds: int
    request_timeout_seconds: float
    grounding_relative_tolerance: float
    equity_curve_max_points: int


@dataclass(frozen=True)
class ApiSettings:
    host: str
    port: int


@dataclass(frozen=True)
class Settings:
    database: DatabaseSettings
    market_data: MarketDataSettings
    windows: EvaluationWindowSettings
    trading: TradingSettings
    training: TrainingSettings
    analysis: AnalysisSettings
    assistant: AssistantSettings
    api: ApiSettings
    dashboard_data_dir: Path
    evaluation_reports_dir: Path


def _read(name: str, default: str | None = None) -> str:
    """The setting's value, or `default` when unset or blank. No default means required."""
    value = (os.getenv(name) or "").strip()
    if value:
        return value
    if default is None:
        raise RuntimeError(f"Missing setting {name}. Copy .env.example to .env and fill it in.")
    return default


def _read_date(name: str, default: str | None = None) -> date | None:
    raw = _read(name, default)
    return date.fromisoformat(raw) if raw else None


def _read_list(name: str, default: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in _read(name, default).split(",") if item.strip())


def _read_path(name: str, default: str) -> Path:
    path = Path(_read(name, default))
    return path if path.is_absolute() else PROJECT_ROOT / path


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    settings = Settings(
        database=DatabaseSettings(
            host=_read("DATABASE_HOST", "localhost"),
            port=int(_read("DATABASE_PORT", "5432")),
            name=_read("DATABASE_NAME", "rl_strategy_lab"),
            writer_user=_read("DATABASE_WRITER_USER", "rl_writer"),
            writer_password=_read("DATABASE_WRITER_PASSWORD"),
            reader_user=_read("DATABASE_READER_USER", "rl_reader"),
            reader_password=_read("DATABASE_READER_PASSWORD"),
        ),
        market_data=MarketDataSettings(
            tickers=tuple(t.upper() for t in _read_list("TICKERS", "NVDA,AMD,INTC")),
            history_start=_read_date("HISTORY_START", "2021-01-01"),
            history_end=_read_date("HISTORY_END", ""),
        ),
        windows=EvaluationWindowSettings(
            train_start=_read_date("TRAIN_START", "2021-01-01"),
            train_end=_read_date("TRAIN_END", "2024-12-31"),
            test_start=_read_date("TEST_START", "2025-01-01"),
            test_end=_read_date("TEST_END", "2025-12-31"),
        ),
        trading=TradingSettings(
            buy_fee_rate=float(_read("BUY_FEE_RATE")),
            sell_fee_rate=float(_read("SELL_FEE_RATE")),
            observation_window_days=int(_read("OBSERVATION_WINDOW_DAYS", "2")),
        ),
        training=TrainingSettings(
            algorithms=_read_list("ALGORITHMS", ",".join(ALGORITHMS)),
            feature_sets=_read_list("FEATURE_SETS", ",".join(FEATURE_SETS)),
            seeds=tuple(int(s) for s in _read_list("SEEDS", "0,1,2,3,4")),
            timesteps=int(_read("TRAIN_TIMESTEPS", "20000")),
            torch_threads=int(_read("TORCH_THREADS", "1")),
            models_dir=_read_path("MODELS_DIR", "data/models"),
        ),
        analysis=AnalysisSettings(
            risk_free_rate=float(_read("RISK_FREE_RATE", "0")),
            confidence_level=float(_read("CONFIDENCE_LEVEL", "0.95")),
            bootstrap_samples=int(_read("BOOTSTRAP_SAMPLES", "10000")),
            bootstrap_block_days=int(_read("BOOTSTRAP_BLOCK_DAYS", "10")),
            bootstrap_random_seed=int(_read("BOOTSTRAP_RANDOM_SEED", "0")),
        ),
        assistant=AssistantSettings(
            ollama_host=_read("OLLAMA_HOST", "http://localhost:11434"),
            model=_read("ASSISTANT_MODEL", "qwen3:8b"),
            temperature=float(_read("ASSISTANT_TEMPERATURE", "0")),
            max_tool_rounds=int(_read("ASSISTANT_MAX_TOOL_ROUNDS", "4")),
            request_timeout_seconds=float(_read("ASSISTANT_REQUEST_TIMEOUT_SECONDS", "180")),
            grounding_relative_tolerance=float(_read("GROUNDING_RELATIVE_TOLERANCE", "0.001")),
            equity_curve_max_points=int(_read("EQUITY_CURVE_MAX_POINTS", "30")),
        ),
        api=ApiSettings(host=_read("API_HOST", "127.0.0.1"), port=int(_read("API_PORT", "8000"))),
        dashboard_data_dir=_read_path("DASHBOARD_DATA_DIR", "web/public/data"),
        evaluation_reports_dir=_read_path("EVALUATION_REPORTS_DIR", "evals/results"),
    )
    _validate(settings)
    return settings


def _validate(s: Settings) -> None:
    w = s.windows
    if not (w.train_start <= w.train_end < w.test_start <= w.test_end):
        raise RuntimeError("Dates must satisfy TRAIN_START <= TRAIN_END < TEST_START <= TEST_END")
    if s.market_data.history_start > w.train_start:
        raise RuntimeError("HISTORY_START must be on or before TRAIN_START")
    for name, rate in (("BUY_FEE_RATE", s.trading.buy_fee_rate), ("SELL_FEE_RATE", s.trading.sell_fee_rate)):
        if not 0 <= rate < 0.1:
            raise RuntimeError(f"{name}={rate} looks wrong: use a fraction, e.g. 0.001 for 0.1%")
    unknown = set(s.training.algorithms) - set(ALGORITHMS)
    if unknown:
        raise RuntimeError(f"ALGORITHMS has unknown values {sorted(unknown)}; allowed: {ALGORITHMS}")
    unknown = set(s.training.feature_sets) - set(FEATURE_SETS)
    if unknown:
        raise RuntimeError(f"FEATURE_SETS has unknown values {sorted(unknown)}; allowed: {FEATURE_SETS}")
    if not 0.5 < s.analysis.confidence_level < 1:
        raise RuntimeError("CONFIDENCE_LEVEL must be between 0.5 and 1, e.g. 0.95")
    minimums = {
        "OBSERVATION_WINDOW_DAYS": (s.trading.observation_window_days, 1),
        "TRAIN_TIMESTEPS": (s.training.timesteps, 1),
        "TORCH_THREADS": (s.training.torch_threads, 1),
        "BOOTSTRAP_SAMPLES": (s.analysis.bootstrap_samples, 100),
        "BOOTSTRAP_BLOCK_DAYS": (s.analysis.bootstrap_block_days, 1),
        "ASSISTANT_MAX_TOOL_ROUNDS": (s.assistant.max_tool_rounds, 1),
        "EQUITY_CURVE_MAX_POINTS": (s.assistant.equity_curve_max_points, 2),
    }
    for name, (value, minimum) in minimums.items():
        if value < minimum:
            raise RuntimeError(f"{name}={value} is too small; it must be at least {minimum}")
    if not s.market_data.tickers or not s.training.seeds or not s.training.algorithms or not s.training.feature_sets:
        raise RuntimeError("TICKERS, SEEDS, ALGORITHMS and FEATURE_SETS must each list at least one value")
    if not 0 <= s.assistant.grounding_relative_tolerance < 0.1:
        raise RuntimeError("GROUNDING_RELATIVE_TOLERANCE must be a small fraction, e.g. 0.001")
    if s.assistant.temperature < 0 or s.assistant.request_timeout_seconds <= 0:
        raise RuntimeError("ASSISTANT_TEMPERATURE must be >= 0 and ASSISTANT_REQUEST_TIMEOUT_SECONDS > 0")
