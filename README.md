# RL Strategy Lab

Can a reinforcement-learning agent trading one stock beat simply buying it and holding it?
This project trains **A2C, DQN and PPO** agents on **NVDA, AMD and INTC**, compares every one with
buy-and-hold under the same fees, stores all results in **PostgreSQL**, and lets a local **Qwen**
model answer questions about them through fixed database tools, with every number in its answers
checked against the data. It is rebuilt from an earlier thesis project (see *Corrections* below).

## Findings

90 agents: 3 algorithms × 2 feature sets × 3 tickers × 5 seeds, trained on 2021–2024 and tested on
2025 (250 trading days), then run unchanged on 2026-01-02 to 2026-11-04 (212 trading days).
Fees are 0.1% per buy and per sell for agents and buy-and-hold alike.

- **No strategy beat buy-and-hold with 95% confidence**, in the test year or in the forward period
  (0 of 18 strategies in each). A strategy's seeds are averaged as one portfolio, and it counts as
  beating buy-and-hold only if the whole confidence interval of its excess return is above zero.
- **Test year 2025:** buy-and-hold returned +34.6% (NVDA), +77.2% (AMD) and +82.1% (INTC). Only one
  strategy had a positive point estimate: DQN with standard features on NVDA, +2.7% versus
  buy-and-hold, with an interval of −13.7% to +22.0%, so it is indistinguishable from luck.
  18 of 90 individual seeds ended above buy-and-hold.
- **Forward period 2026 (performance since training):** buy-and-hold returned +6.0% (NVDA),
  +118.3% (AMD) and +47.7% (INTC). Three strategies had small positive point estimates (the largest,
  DQN with indicators on INTC, +3.8%), all with intervals spanning zero. 19 of 90 seeds ended above
  buy-and-hold.
- **Seeds matter more than settings.** The same configuration can end anywhere from 0% to above
  buy-and-hold depending on the random seed (see the seed-spread chart in
  `notebooks/results_analysis.ipynb`). 13 of 90 agents never traded in the test year and 28 held
  the stock more than 95% of the time, i.e. they learned "stay out" or "buy and hold".
- **The indicator features (SMA, RSI, OBV) did not help consistently.** They did better than the
  standard features on INTC in the test year and worse on NVDA.

The whole grid trains in about 11 minutes on a MacBook M3 CPU (7 seconds per agent).

**The assistant** (`qwen3:8b`, 32-question evaluation in `evals/assistant_questions.json`):


| Measure | Result |
| --- | --- |
| Tool-selection accuracy (28 answerable questions) | 100% |
| Answer correctness: the key figure matches plain SQL | 92.9% (26 of 28) |
| Grounded on the first attempt: every number matched tool output | 90.6% (29 of 32) |
| Grounded after at most one retry | 93.8% (30 of 32) |
| Fell back to the raw table | 6.3% (2 of 32) |
| Out-of-scope questions declined (forecasts, other tickers, advice) | 100% (4 of 4) |
| Median / 90th-percentile latency on a MacBook M3 | 37 s / 58 s |

Both misses were caught by the grounding check, so the user saw verified tool results instead of
a wrong summary. In one, Qwen claimed 0 seeds beat buy-and-hold when the data says 1. In the
other, it misspelled "A2C" as "A20C".

The check is deliberately strict. It compares numbers at face value and requires a written sign
to match. An earlier, looser version scored higher (100% correctness) but would also have let a
number 100 times too large, or a gain described as a loss, through. Earlier runs also led to two
tool fixes: the ranking tool now sorts `highest_first` / `lowest_first` (best first by default),
and it filters by ticker only when the question names one.
Report: `evals/results/assistant_qwen3-8b_2026-11-05.json`.

## How it works

```
 make ingest / refresh          make train / forward-test             make run / snapshot
┌─────────────────────┐      ┌───────────────────────────────┐      ┌───────────────────────────────┐
│ market_data/        │      │ trading/                      │      │ assistant/  +  api_server.py  │
│ Yahoo Finance daily │─────▶│ custom Buy/Sell/Hold env      │      │ Qwen (Ollama) calls 6 fixed   │
│ prices, checked     │      │ A2C · DQN · PPO, 5 seeds      │      │ read-only queries; grounding  │
└─────────┬───────────┘      │ metrics, buy-and-hold,        │      │ check on every number         │
          │ writer role      │ bootstrap comparison          │      └───────────────┬───────────────┘
          ▼                  └──────────────┬────────────────┘                      │ read-only role
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ PostgreSQL: daily_prices, training_runs, run_metrics, run_equity_curves, buy_and_hold_*,         │
│ strategy_baseline_comparisons, assistant_requests; views current_training_runs, strategy_results │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
                                         │ make snapshot (JSON)
                                         ▼
                         web/ — static Next.js dashboard (Vercel), no backend
```

- **Environment** (`src/trading/trading_environment.py`): each trading day the agent sees the last
  2 days of features plus whether it holds the stock, and chooses Buy, Sell or Hold at the close.
  Long-only, all-in or all-out. Buying while holding is a free Hold. Fees are charged only when the
  position changes. The reward is the day's log return minus the log fee, so rewards sum exactly to
  the reported profit. An open position is sold on the last day, like buy-and-hold's round trip.
- **Buy-and-hold** runs through the same environment (buy on day one, hold), so it pays the same
  fees on the same days.
- **Features** (`src/market_data/feature_engineering.py`) are scale-free and use only past data.
  *standard*: close log return, open/high/low relative to close, volume vs its 20-day mean.
  *indicators*: standard plus the gap to SMA(12), RSI(14) and 12-day on-balance-volume flow.
  Both sets trade on the adjusted close and cover exactly the same days.
- **Metrics** (`src/trading/performance_metrics.py`): total return, annualised Sharpe ratio, max
  drawdown (a positive fraction), trade count, win rate per buy→sell round trip, and exposure.
- **Comparison** (`src/trading/strategy_comparison.py`): excess return = (1 + strategy return) /
  (1 + buy-and-hold return) − 1, with a moving-block bootstrap interval (10-day blocks, 10,000
  samples) over the daily return differences.
- **Assistant** (`src/assistant/`): Qwen never writes SQL and never states a number from memory.
  It picks one of six tools (`list_strategies`, `get_metrics`, `compare_to_baseline`,
  `rank_strategies`, `get_equity_curve`, `data_freshness`). Each validates its arguments and runs
  one parameterized query as the read-only role. Qwen then answers as JSON (an answer plus a list of
  claims), and the grounding check confirms that every number and date appears in the tool output,
  at face value and with the sign as written.
  A failure gets one retry. If that fails too, the response carries the raw tool results instead.

## Setup (macOS, no Docker)

Needs Python 3.11, a local PostgreSQL your macOS user can administer (Homebrew `postgresql@15` on
port 5433 here), Ollama, and Node.js for the dashboard.

```bash
make setup                       # virtual environment + pinned dependencies
cp .env.example .env             # then set the two database passwords
make database                    # database, writer + read-only roles, migrations (safe to re-run)
make ingest && make check-data   # ~5 years of daily prices, then 23 data checks
make test                        # unit tests
make train                       # the 90-agent grid (~11 min); re-running skips stored agents
make forward-test                # run the agents on days after the test window
make analysis                    # re-run notebooks/results_analysis.ipynb

ollama pull qwen3:8b             # 5.2 GB; Ollama must be running (ollama serve)
make eval-assistant              # 32 questions, writes evals/results/assistant_*.json
make run                         # API at http://127.0.0.1:8000/docs

make snapshot                    # export results + curated answers to web/public/data
make web-install && make web-dev # dashboard at http://localhost:3000
```

Day to day: `make refresh` downloads new prices and forward-tests every agent on them; then
`make snapshot` and rebuild the site. `make help` lists every target.

**Deploying the dashboard:** import the repository in Vercel with the root directory set to `web/`.
The site is fully static and contains only exported results, no credentials.

## Configuration

Every setting lives in `.env` (never committed); `.env.example` documents each one, and
`src/settings.py` is the only code that reads them. The main ones:

| Setting | Default | Meaning |
| --- | --- | --- |
| `TICKERS` | NVDA,AMD,INTC | Stocks to download and trade |
| `TRAIN_START`…`TEST_END` | 2021–2024 / 2025 | Training and test windows; later days are the forward period |
| `BUY_FEE_RATE`, `SELL_FEE_RATE` | 0.001 | Fee per trade as a fraction (0.1%) |
| `ALGORITHMS`, `FEATURE_SETS`, `SEEDS` | all / all / 0–4 | The training grid |
| `TRAIN_TIMESTEPS` | 20000 | Training steps per agent |
| `OBSERVATION_WINDOW_DAYS` | 2 | Past days of features the agent sees |
| `CONFIDENCE_LEVEL`, `BOOTSTRAP_*` | 0.95, 10,000 samples, 10-day blocks | Buy-and-hold comparison |
| `ASSISTANT_MODEL` | qwen3:8b | Ollama model tag |
| `GROUNDING_RELATIVE_TOLERANCE` | 0.001 | Slack on top of the rounding a written number implies |

The feature definitions (SMA 12, RSI 14, …) are named constants in `feature_engineering.py`, not
settings, because changing them changes what the results mean.

## Project layout

```
src/
  settings.py                 all settings, from .env
  experiment_options.py       algorithm, feature-set and period names
  database.py                 writer and read-only connections
  database_migrations.py      applies sql/migrations in order
  market_data/                price_download, price_history, feature_engineering, price_quality_checks
  trading/                    trading_environment, agent_training, performance_metrics,
                              results_store, experiment_grid, forward_test, strategy_comparison
  assistant/                  result_queries (the 6 tools), results_assistant (Qwen loop),
                              grounding_check, answer_schema, request_log, assistant_evaluation
  api_server.py               FastAPI: GET /metrics, GET /compare, POST /ask
  dashboard_snapshot.py       exports web/public/data/*.json
  portfolio_summary.py        exports the results summary shown on the portfolio website
sql/migrations/               numbered schema changes (never edit an applied one; add a new file)
notebooks/results_analysis.ipynb
evals/assistant_questions.json, evals/results/   evaluation inputs and dated reports
web/                          Next.js static dashboard
tests/                        one test file per module
```

## Database

| Table / view | One row per |
| --- | --- |
| `daily_prices`, `price_ingest_log` | ticker and trading day; download |
| `training_runs` | trained agent (unique on its full configuration) |
| `run_metrics`, `run_equity_curves` | agent and evaluation period (`test` or `forward`); day |
| `buy_and_hold_baselines`, `buy_and_hold_equity_curves` | ticker and period; day |
| `strategy_baseline_comparisons` | strategy (ticker + algorithm + feature set) and period |
| `assistant_requests` | question asked through the API or the evaluation |
| `current_training_runs` (view) | newest run per algorithm, feature set, ticker and seed |
| `strategy_results` (view) | strategy and period: mean and spread of each metric across seeds |

The writer role owns the tables. The read-only role (used by the tools, API and notebook) can only
`SELECT`, which `tests/test_database_roles.py` checks.

## Evals

| Layer | Where | What is checked |
| --- | --- | --- |
| Data | `make check-data` | Row counts, no missing days, OHLC consistency, split adjustment, known closes, Open/Close not swapped |
| Features | `tests/test_feature_engineering.py` | No look-ahead; both sets cover the same days, including days with an unchanged close |
| Environment | `tests/test_trading_environment.py` | Free no-op trades, fees only on position changes, rewards sum to profit, no future data |
| Metrics | `tests/test_performance_metrics.py`, `test_strategy_comparison.py` | Hand-checked equity curves, bootstrap interval |
| Training | `tests/test_agent_training.py` | Buy-and-hold equals one round trip; same seed gives an identical agent |
| Tools | `tests/test_result_queries.py` | Bad arguments rejected before any query; rows match plain SQL |
| Grounding | `tests/test_grounding_check.py` | Made-up numbers and dates are caught; honest rounding passes |
| Assistant | `tests/test_results_assistant.py`, `make eval-assistant` | Tool loop, retry, fallback; accuracy on 32 questions |
| Database | `tests/test_database_roles.py` | Read-only role cannot insert, update, delete, drop or create |

Reports are written to `evals/results/` with the date in the file name.

## Corrections relative to the thesis notebooks

- The thesis CSVs have **Open and Close swapped**: yfinance returns columns as Close, High, Low,
  Open, Volume, and the notebook renamed them by position. Here columns are selected by name and
  checked by `make check-data`.
- The indicator variant traded on `Low`. Here both variants trade on the adjusted close.
- gym-anytrading's fees were implicit. Here they are explicit settings, applied to buy-and-hold too.
- The thesis compared single runs on a 34-day window. Here every configuration has 5 seeds, a
  250-day test year, a forward period and a confidence interval.

## Limits

- Forward results are "performance since training", not retraining; they cover one market regime.
- yfinance is unofficial and can lag or rate-limit; `data_freshness` and the dashboard show the
  latest stored date.
- On a 16 GB MacBook M3, `qwen3:8b` takes 30 to 60 seconds per question (three to four model calls).
  The public dashboard therefore shows pre-generated answers; the live assistant runs locally.
