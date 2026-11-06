# RL Strategy Lab: Project Guide

This guide shows how to set up, run and use the project step by step, and explains every finance and
machine-learning idea it relies on, with worked examples. For the findings, read the
[README](README.md).

**Contents**
1. [What the project does](#1-what-the-project-does)
2. [Setup](#2-setup)
3. [Configuration](#3-configuration)
4. [Running the pipeline](#4-running-the-pipeline)
5. [Using the results](#5-using-the-results)
6. [Day-to-day operations](#6-day-to-day-operations)
7. [Finance concepts, formulas and examples](#7-finance-concepts-formulas-and-examples)
8. [Machine-learning concepts](#8-machine-learning-concepts)
9. [How the assistant stays honest](#9-how-the-assistant-stays-honest)
10. [Troubleshooting](#10-troubleshooting)
11. [Glossary](#11-glossary)

---

## 1. What the project does

It asks one question: **can a computer program that learns by trial and error trade a stock
better than simply buying it and holding it?**

1. It downloads about five years of daily prices for three stocks (NVDA, AMD, INTC).
2. It trains 90 trading agents: 3 learning algorithms × 2 sets of inputs × 3 stocks × 5 random seeds.
   Each agent decides every day whether to **buy**, **sell** or **hold**.
3. It tests every agent on a year it never saw (2025), and again on 2026 so far.
4. It compares each one with **buy-and-hold** under the same trading fees, and tests whether any
   difference is likely real or just luck.
5. It stores everything in PostgreSQL. A local AI model (Qwen) answers questions about the results,
   and every number it states is checked against the database.
6. A static website shows the results to anyone, with no server or database behind it.

**Use cases**
- Research: an honest, reproducible test of whether RL trading beats a passive strategy.
- Analysis: query results in SQL, in the notebook, through the API, or by asking the assistant.
- Demonstration: a public dashboard, plus a live local assistant whose answers are verified.

---

## 2. Setup

Everything runs natively on macOS. There is no Docker.

### 2.1 Install the tools (once)

| Tool | Why | Install |
| --- | --- | --- |
| Python 3.11 | Runs everything except the website | `brew install python@3.11` |
| PostgreSQL 15 | Stores prices and results | `brew install postgresql@15` |
| Ollama | Runs the Qwen model locally | `brew install ollama` |
| Node.js 20+ | Builds the website | `brew install node` |

This machine runs PostgreSQL 15 on **port 5433**, because another PostgreSQL server already uses
5432. To set the port: `brew services start postgresql@15`, then set `port = 5433` in
`/opt/homebrew/var/postgresql@15/postgresql.conf` and restart.

### 2.2 Create the Python environment

```bash
cd ~/Desktop/Work/rl-strategy-lab
make setup                 # creates .venv and installs requirements.txt
```

### 2.3 Create your settings file

```bash
cp .env.example .env
```

Open `.env` and set `DATABASE_WRITER_PASSWORD` and `DATABASE_READER_PASSWORD` (pick any two
passwords). Change `DATABASE_PORT` if your PostgreSQL is not on 5433. Every other setting has a
working default; see [section 3](#3-configuration).

### 2.4 Create the database

```bash
make database
```

This runs [scripts/setup_database.sh](scripts/setup_database.sh), which:
1. creates two login roles: the **writer** (`rl_writer`), which can change data, and the **reader**
   (`rl_reader`), which can only read it;
2. creates the database `rl_strategy_lab`, owned by the writer;
3. applies every file in [sql/migrations/](sql/migrations/) in order, recording each one in the
   `schema_migrations` table;
4. gives the reader `SELECT` on all current and future tables.

It is safe to run again at any time.

### 2.5 Download prices and check them

```bash
make ingest        # ~5 years of daily prices for every ticker
make check-data    # 23 checks; must say "23/23 checks passed"
```

### 2.6 Get the AI model (only needed for the assistant)

```bash
ollama serve &           # or: brew services start ollama
ollama pull qwen3:8b     # 5.2 GB download
```

### 2.7 Install the website (only needed for the dashboard)

```bash
make web-install
```

### 2.8 Confirm everything works

```bash
make test          # 86 tests; database tests skip if Postgres is not set up
```

---

## 3. Configuration

All settings live in `.env`, which is never committed. [.env.example](.env.example) documents each
one. Only [src/settings.py](src/settings.py) reads them, and it rejects impossible values (for
example a fee of 5, or a test year that starts before training ends).

| Group | Setting | Default | What it controls |
| --- | --- | --- | --- |
| Database | `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME` | localhost, 5432, rl_strategy_lab | Where PostgreSQL is |
| | `DATABASE_WRITER_*`, `DATABASE_READER_*` | rl_writer / rl_reader | The two roles and their passwords |
| Market data | `TICKERS` | NVDA,AMD,INTC | Which stocks to download and trade |
| | `HISTORY_START`, `HISTORY_END` | 2021-01-01, empty (= today) | How much history to download |
| Windows | `TRAIN_START`, `TRAIN_END` | 2021-01-01 to 2024-12-31 | Days the agents learn from |
| | `TEST_START`, `TEST_END` | 2025-01-01 to 2025-12-31 | The held-out test year; later days are the forward period |
| Trading | `BUY_FEE_RATE`, `SELL_FEE_RATE` | 0.001 (0.1%) | Cost of each buy and each sell |
| | `OBSERVATION_WINDOW_DAYS` | 2 | How many past days the agent sees |
| Training | `ALGORITHMS`, `FEATURE_SETS`, `SEEDS` | A2C,DQN,PPO; standard,indicators; 0–4 | The grid of agents |
| | `TRAIN_TIMESTEPS` | 20000 | Practice steps per agent |
| | `TORCH_THREADS`, `MODELS_DIR` | 1, data/models | CPU threads; where models are saved |
| Analysis | `RISK_FREE_RATE` | 0 | Annual cash interest used in the Sharpe ratio |
| | `CONFIDENCE_LEVEL`, `BOOTSTRAP_SAMPLES`, `BOOTSTRAP_BLOCK_DAYS`, `BOOTSTRAP_RANDOM_SEED` | 0.95, 10000, 10, 0 | The buy-and-hold significance test |
| Assistant | `OLLAMA_HOST`, `ASSISTANT_MODEL` | localhost:11434, qwen3:8b | Which model answers |
| | `ASSISTANT_TEMPERATURE`, `ASSISTANT_MAX_TOOL_ROUNDS`, `ASSISTANT_REQUEST_TIMEOUT_SECONDS` | 0, 4, 180 | How it answers |
| | `GROUNDING_RELATIVE_TOLERANCE`, `EQUITY_CURVE_MAX_POINTS` | 0.001, 30 | How strictly numbers are checked; size of chart data sent to it |
| API and outputs | `API_HOST`, `API_PORT` | 127.0.0.1, 8000 | Where the API listens |
| | `DASHBOARD_DATA_DIR`, `EVALUATION_REPORTS_DIR` | web/public/data, evals/results | Where exports and reports go |

**Examples**
- Try different fees: set `BUY_FEE_RATE=0.0005` and `SELL_FEE_RATE=0.0005`, then `make train`. The
  new configuration trains new agents; the old ones stay in the database, and the summaries show
  the newest run for each seed.
- Add a stock: add it to `TICKERS`, run `make ingest`, add a known closing price for it in
  [price_quality_checks.py](src/market_data/price_quality_checks.py), then `make train`.
- Quick experiment: `ALGORITHMS=PPO SEEDS=0 make train` trains only PPO with seed 0.

The feature definitions (12-day SMA, 14-day RSI and so on) are named constants in
[feature_engineering.py](src/market_data/feature_engineering.py), not settings, because changing
them changes what the results mean.

---

## 4. Running the pipeline

Run these in order the first time. `make help` lists every command.

| Step | Command | Time | What happens |
| --- | --- | --- | --- |
| 1 | `make train` | ~11 min | Trains and tests all 90 agents, computes buy-and-hold, compares them. Re-running skips agents already stored. |
| 2 | `make forward-test` | ~1 min | Runs every saved agent on the days after the test year. |
| 3 | `make analysis` | ~30 s | Re-runs [notebooks/results_analysis.ipynb](notebooks/results_analysis.ipynb): tables, charts and a one-sentence verdict. |
| 4 | `make eval-assistant` | ~30 min | Asks Qwen the 32 questions in [evals/assistant_questions.json](evals/assistant_questions.json) and scores the answers. |
| 5 | `make snapshot` | ~8 min | Exports results and 8 pre-generated answers to `web/public/data/`. |
| 6 | `make web-build` | ~30 s | Builds the static website into `web/out/`. |

**One agent only:**
`make train-one ALGORITHM=PPO TICKER=NVDA FEATURE_SET=indicators SEED=0`.

**Retrain agents that already exist:**
`.venv/bin/python -m src.trading.experiment_grid --feature-set indicators --replace`.

---

## 5. Using the results

### 5.1 The dashboard (public)
`make web-dev`, then open http://localhost:3000. It shows the headline verdict, a filterable table
of every strategy, an equity chart, the excess-return intervals, each seed's return, the
pre-generated assistant answers with their tool calls and checks, and the evaluation scores.

**Deploy:** on vercel.com, import the repository and set the root directory to `web/`. Rebuild
after every `make snapshot`, because the data is built into the pages.

### 5.2 The API (local)
```bash
make run          # Ollama must be running for /ask
```
Open http://127.0.0.1:8000/docs to try each endpoint in the browser.

| Endpoint | Example | Returns |
| --- | --- | --- |
| `GET /metrics` | `/metrics?ticker=NVDA&algorithm=PPO&feature_set=indicators&period=test` | One strategy's metrics across its seeds |
| `GET /compare` | `/compare?ticker=AMD&period=forward` | Every strategy on that ticker against buy-and-hold |
| `POST /ask` | `{"question": "Which strategy had the lowest drawdown on NVDA?"}` | The answer, the tool calls made and the number checks (~1 min) |
| `GET /health` | `/health` | `{"status": "ok"}` |

Invalid input (an unknown ticker or algorithm) returns HTTP 422 with the reason. If nothing is
stored for valid input, you get 404. If the model is unavailable, `/ask` returns 503.

### 5.3 One question from the terminal
```bash
.venv/bin/python -m src.assistant.results_assistant "Did any strategy beat buy-and-hold on AMD?"
```

### 5.4 SQL
Connect as the read-only role: `psql -h localhost -p 5433 -U rl_reader rl_strategy_lab`.
```sql
-- every strategy against buy-and-hold in the test year
SELECT ticker, algorithm, feature_set,
       round(100 * strategy_return::numeric, 1)     AS strategy_pct,
       round(100 * buy_and_hold_return::numeric, 1) AS buy_and_hold_pct,
       round(100 * excess_return::numeric, 1)       AS excess_pct,
       beats_buy_and_hold
FROM strategy_baseline_comparisons
WHERE evaluation_period = 'test'
ORDER BY excess_return DESC;
```
In pgAdmin, the server **RL Strategy Lab (PG15)** connects as `rl_reader`.

---

## 6. Day-to-day operations

| Task | Command |
| --- | --- |
| Add the newest trading days, check them, and forward-test every agent on them | `make refresh` |
| Publish the update | `make snapshot`, then `make web-build` (or push, so Vercel rebuilds) |
| Change the schema | Add a new file such as `sql/migrations/0004_add_x.sql`, then `make migrate`. Never edit an applied migration. |
| Recompute the buy-and-hold comparisons only | `make compare` |
| Compare a smaller model | `make eval-assistant MODEL=qwen3:4b` |
| Update the numbers on the portfolio website | `make portfolio-summary`, then rebuild the portfolio |

`make refresh` stores completed days only (up to yesterday), so a half-finished trading day is
never saved. It also re-downloads the last week. If those prices changed (a split or dividend
re-adjusted the history), it downloads that ticker's full history again.

A buy-and-hold comparison needs at least 31 trading days (3 bootstrap blocks of 10 days, plus 1).
Shorter forward periods get metrics but no comparison until enough days have passed.

Reports are written to [evals/results/](evals/results/) with the date in the file name. Every
question asked through the API or the evaluation is logged in the `assistant_requests` table.

---

## 7. Finance concepts, formulas and examples

### 7.1 Stocks, tickers and daily prices
A **stock** is a share of a company. A **ticker** is its short code: NVDA (Nvidia), AMD and INTC
(Intel). Each trading day has five numbers, called **OHLCV**:

| Field | Meaning | Example (NVDA, 2025-01-07) |
| --- | --- | --- |
| Open | First price of the day | $152.63 |
| High | Highest price | $152.73 |
| Low | Lowest price | $139.64 |
| Close | Last price of the day | $139.77 |
| Volume | Shares traded | 351,782,200 |

There are about 252 trading days a year; weekends and market holidays are skipped.

### 7.2 Adjusted prices and stock splits
In June 2024 NVDA did a **10-for-1 split**: each share became 10 shares worth a tenth as much. An
unadjusted chart shows a 90% "crash" that never cost anyone money. **Adjusted** prices rescale
history for splits and dividends, so returns are real. The project downloads adjusted prices, and
`make check-data` fails if any day moves more than 40%.

### 7.3 Returns
- **Simple return** of one day: `close_today / close_yesterday − 1`.
  $100 → $103 is `103/100 − 1 = +3%`.
- **Log return**: `ln(close_today / close_yesterday)`. For small moves it is almost the same
  (+3% ≈ 0.0296). Its useful property is that **log returns add up over days**:
  `ln(103/100) + ln(105/103) = ln(105/100)`. The agent's rewards are log returns for this reason.
- **Total return** over a period: `final value / starting value − 1`.

### 7.4 Equity and the equity curve
**Equity** is what your money is worth. Every strategy starts with equity 1.0 (think $1). An
**equity curve** is equity on every day. Equity 1.35 at the end means +35%.

### 7.5 Trading actions and positions
The agent is either **in the stock** (holding it) or **in cash**:

| Action | If in cash | If holding the stock |
| --- | --- | --- |
| **Buy** | Moves all money into the stock (pays the buy fee) | Nothing happens, no fee (same as Hold) |
| **Sell** | Nothing happens, no fee (same as Hold) | Moves all money into cash (pays the sell fee) |
| **Hold** | Stays in cash | Keeps the stock |

- **Long-only**: it can only profit when the price rises. It cannot **short** (bet on a fall).
- **All-in or all-out**: no partial positions.
- Trades happen at the day's **close**.
- On the last day any open position is sold, so every result is a completed **round trip**
  (buy, then sell).

### 7.6 Trading fees
Each buy and each sell costs 0.1% of the amount traded (`BUY_FEE_RATE`, `SELL_FEE_RATE`).
Buying $1 leaves $0.999 of stock. A full round trip costs about 0.2%:
`1 × 0.999 × 0.999 = 0.998`. Fees punish agents that trade often, which is realistic.

### 7.7 Buy-and-hold (the baseline)
Buy on the first day, hold, sell on the last day, paying both fees. It runs through the same
trading environment as the agents, so the comparison is fair.

**Worked example (NVDA, test year 2025)**
- First close (2025-01-02): $137.95. Last close (2025-12-31): $186.06.
- Price growth: `186.06 / 137.95 = 1.3488`.
- After both fees: `1.3488 × 0.999 × 0.999 = 1.3461`.
- **Buy-and-hold return = +34.61%**, the number stored in `buy_and_hold_baselines`.

### 7.8 Sharpe ratio (return per unit of risk)
```
Sharpe = (average daily return − daily risk-free rate) / standard deviation of daily returns × √252
```
The **standard deviation** of daily returns measures how much they swing (**volatility**).
Multiplying by √252 turns a daily figure into a yearly one. The risk-free rate (`RISK_FREE_RATE`)
is what cash would earn; it is 0 here.

*Example:* average daily return 0.10% and daily standard deviation 2.0% give
`0.10 / 2.0 × √252 = 0.05 × 15.87 ≈ 0.79`. Rough guide: below 0.5 is weak, around 1 is good,
above 2 is rare. NVDA buy-and-hold in 2025 had a Sharpe ratio of 0.85. If an agent never trades
(no variation at all), its Sharpe ratio is undefined and stored as empty.

### 7.9 Maximum drawdown (the worst fall)
The largest drop from a peak to a later low, as a positive percentage:
```
drawdown on a day = 1 − equity that day / highest equity so far
max drawdown      = the largest of these
```
*Example:* equity 1.00 → 1.20 → 0.90 → 1.30. The peak 1.20 falls to 0.90:
`1 − 0.90 / 1.20 = 25%`. NVDA buy-and-hold fell 36.9% from its peak during 2025 before recovering.
Lower is better.

### 7.10 Trade count, round trips, win rate, exposure
- **Trade count**: every buy and every sell. Buy-and-hold makes 2.
- **Round trip**: one buy followed by one sell.
- **Win rate**: share of round trips that made money after both fees. Trips +5%, −1%, +2% and
  −3% give a 50% win rate.
- **Exposure**: share of days spent holding the stock. 100% is like buy-and-hold; 0% means the
  agent never invested.

### 7.11 Excess return over buy-and-hold
```
excess return = (1 + strategy return) / (1 + buy-and-hold return) − 1
```
This is how much more (or less) money the strategy ended with, relative to buy-and-hold.

*Example (NVDA, DQN with standard features, test year):* the five seeds averaged +38.19%, and
buy-and-hold made +34.61%: `1.3819 / 1.3461 − 1 = +2.66%`.

A strategy's seeds are combined as an equal-weight portfolio: put $1 in each of the 5 agents and
average their equity curves.

### 7.12 Confidence interval and the block bootstrap ("is it luck?")
One year of prices is one sample of history. A strategy can beat buy-and-hold by luck, so the
project asks how much the excess return would vary under slightly different luck:

1. For each trading day, take the strategy's daily log return minus buy-and-hold's.
2. **Bootstrap**: build 10,000 imaginary years by re-drawing those daily differences at random.
3. **Block** bootstrap: draw them in runs of 10 consecutive days rather than one at a time,
   because market days are not independent (calm and stormy weeks cluster).
4. Each imaginary year gives an excess return. The middle 95% of them is the **95% confidence
   interval**.

**Beats buy-and-hold** means the whole interval is above zero. The NVDA DQN example above was
+2.66%, but its interval runs from −13.7% to +22.0%: it could easily be luck, so it does not count.

### 7.13 Train, test and forward periods
| Period | Dates | Used for |
| --- | --- | --- |
| Train | 2021-01-01 to 2024-12-31 | The agent learns |
| Test | 2025-01-01 to 2025-12-31 | Scored once, never learned from |
| Forward | 2026-01-02 onward | "Performance since training": `make refresh` adds new days |

Testing on unseen data matters because an agent can memorise its training years (**overfitting**)
and still fail on new ones. The test windows are chosen by date, never by row number.

### 7.14 Look-ahead bias
Using information that would not have been available at the time, such as tomorrow's price
inside today's decision. It makes backtests look far better than reality. Here every feature uses
only the current and earlier days, and tests confirm that changing future data leaves today's
inputs unchanged.

### 7.15 Technical indicators (the "indicators" feature set)
- **SMA(12), simple moving average**: the average close of the last 12 days. The agent sees
  `close / SMA − 1`; +5% means the price is 5% above its recent average, a sign of momentum.
- **RSI(14), relative strength index**: compares recent gains with recent losses on a 0–100
  scale: `RSI = 100 − 100 / (1 + average gain / average loss)` over 14 days. Above 70 is often
  called overbought, below 30 oversold. The agent sees it rescaled to −1…+1.
- **OBV, on-balance volume**: a running total that adds the day's volume on an up close,
  subtracts it on a down close, and adds nothing on an unchanged close. The agent sees the 12-day
  change in OBV divided by the 12-day total volume (−1…+1); +1 means all recent volume came on up
  days, a sign of buying pressure.
- The **standard** set uses only price and volume: the daily log return, the open, high and low
  relative to the close, and volume compared with its 20-day average.

*Example (OBV flow):* over 3 days with volumes 100, 200 and 100 and closes up, down and up, the
signed volume is `+100 − 200 + 100 = 0` out of 400 total, so the flow is 0 (balanced).

---

## 8. Machine-learning concepts

| Term | Meaning here |
| --- | --- |
| **Reinforcement learning (RL)** | Learning by trial and error: try actions, receive rewards, do more of what paid off. |
| **Agent** | The decision-maker: a small neural network that picks Buy, Sell or Hold. |
| **Environment** | The simulated market in [trading_environment.py](src/trading/trading_environment.py). It applies the action, charges fees and moves to the next day. |
| **Observation** | What the agent sees each day: the last 2 days of features plus a flag saying whether it holds the stock. |
| **Reward** | The day's log return if holding, minus the log of any fee paid. The rewards of a year add up exactly to `ln(final equity)`, so the agent optimises exactly the profit that is reported. |
| **Episode** | One pass through the training years, from the first day to the last. |
| **Timesteps** | Total days of practice (20,000 is about 20 passes through the four training years). |
| **Policy** | The agent's rule for choosing actions. At test time it picks its single best action (deterministic). |
| **Seed** | The starting point of the random numbers. Different seeds give different agents from the same settings, so the project trains 5 seeds per configuration and reports their spread. The same seed always gives the same agent. |
| **A2C** (Advantage Actor-Critic) | Learns a policy (the actor) and an estimate of how good each situation is (the critic) at the same time. |
| **DQN** (Deep Q-Network) | Learns the value of each action in each situation, then picks the most valuable action. |
| **PPO** (Proximal Policy Optimization) | Like A2C, but limits how much the policy can change in one update, which makes learning steadier. |

All three come from the stable-baselines3 library and train on the CPU (about 7 seconds per agent).

---

## 9. How the assistant stays honest

```
question → Qwen picks a tool → the tool runs one fixed, read-only SQL query → Qwen answers as JSON
         → grounding check: is every number and date in the answer present in the tool output?
              yes → return the answer
              no  → one retry with the problems listed → still no → return the raw tool results
```

- Qwen can only use six tools, defined in [result_queries.py](src/assistant/result_queries.py),
  and never writes SQL. Arguments are validated first, so "TSLA" or "SAC" are rejected before any
  query runs.
- The tools connect as the read-only role, so even a misbehaving model cannot change data.
- The grounding check in [grounding_check.py](src/assistant/grounding_check.py) allows honest
  rounding ("28.9%" for 28.87) but rejects anything else:
  - numbers are compared at face value ("0.29%" does not pass for 28.87%);
  - a written sign must match ("lost −28.87%" fails if the tool says +28.87), while unsigned
    wording such as "4.26% below" may describe a negative value;
  - each claim is checked against the output of the tool it cites.

  Small counts (0–10), numbers and dates repeated from the question, and labels such as SMA(12)
  are not checked.
- It cannot catch a real number attached to the wrong claim (for example the right value for the
  wrong strategy). The 32-question evaluation measures those mistakes separately.

---

## 10. Troubleshooting

| Problem | Fix |
| --- | --- |
| `Missing setting DATABASE_WRITER_PASSWORD` | Create `.env` from `.env.example` and set both passwords. |
| `connection refused` on port 5433 | Start PostgreSQL: `brew services start postgresql@15`, and check `DATABASE_PORT`. |
| `No prices for NVDA. Run make ingest first.` | Run `make ingest`. |
| `fewer than 2 trading days between …` | The date window has no data yet; check `TEST_*` and run `make ingest`. |
| `make refresh` says "no new trading days" | Normal at weekends, on holidays or before the day's close. |
| `/ask` returns 503 | Start Ollama (`ollama serve`) and pull the model (`ollama pull qwen3:8b`). |
| Assistant is slow (~1 min) | Normal for an 8B model on a 16 GB laptop. Try `ASSISTANT_MODEL=qwen3:4b`. |
| An answer says "could not verify" | The grounding check rejected the model's numbers twice. The raw tool results below it are correct. |
| Website shows old numbers | Run `make snapshot`, then rebuild (`make web-build` or redeploy). |
| `Table … has rows; migrate them by hand` | Migration 0002 protects old result tables; this only happens on a database from before November 2026. |

---

## 11. Glossary

| Term | Short meaning |
| --- | --- |
| Adjusted close | Closing price corrected for splits and dividends |
| Baseline | The simple strategy to beat: buy-and-hold |
| Bootstrap | Estimating uncertainty by resampling your own data many times |
| Confidence interval | A range that likely contains the true value (95% of the time) |
| Drawdown | Fall from a previous peak |
| Equity curve | Daily value of the money invested, starting at 1.0 |
| Excess return | How much better or worse than buy-and-hold, relative to it |
| Exposure | Share of days invested in the stock |
| Fee rate | Cost per trade as a fraction (0.001 = 0.1%) |
| Forward period | Days after the test year; performance since training |
| Grounding | Checking that every number stated comes from the data |
| Log return | `ln(price today / price yesterday)`; adds up across days |
| Long-only | Can profit only from rising prices |
| OHLCV | Open, high, low, close, volume |
| Overfitting | Learning the training data too well to generalise |
| Round trip | One buy followed by one sell |
| Sharpe ratio | Return per unit of volatility, annualised |
| Ticker | A stock's short code, such as NVDA |
| Volatility | How much returns swing; their standard deviation |
| Win rate | Share of round trips that made money |
