-- 0001: the first schema (build steps 2-4). Run as the writer role, which owns the tables.
-- Uses IF NOT EXISTS because it was first applied by hand, before migrations were tracked.
-- Read-only grants are applied by scripts/setup_database.sh, which knows the role name.

CREATE TABLE IF NOT EXISTS prices (
    ticker      text             NOT NULL,
    date        date             NOT NULL,
    open        double precision NOT NULL,
    high        double precision NOT NULL,
    low         double precision NOT NULL,
    close       double precision NOT NULL,
    volume      bigint           NOT NULL,
    fetched_at  timestamptz      NOT NULL DEFAULT now(),
    PRIMARY KEY (ticker, date),
    CHECK (low <= high),
    CHECK (low > 0),
    CHECK (volume >= 0)
);

-- One row per ingest call, so "when was the data last refreshed?" has an answer.
CREATE TABLE IF NOT EXISTS ingest_log (
    id            bigserial   PRIMARY KEY,
    ticker        text        NOT NULL,
    mode          text        NOT NULL CHECK (mode IN ('full', 'refresh')),
    requested_from date,
    rows_upserted integer     NOT NULL,
    latest_date   date,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS runs (
    id           bigserial        PRIMARY KEY,
    algo         text             NOT NULL CHECK (algo IN ('A2C', 'DQN', 'PPO')),
    feature_set  text             NOT NULL CHECK (feature_set IN ('standard', 'indicators')),
    ticker       text             NOT NULL,
    seed         integer          NOT NULL,
    train_start  date             NOT NULL,
    train_end    date             NOT NULL,
    test_start   date             NOT NULL,
    test_end     date             NOT NULL,
    timesteps    integer          NOT NULL,
    window_size  integer          NOT NULL,
    model_path   text,
    fee_bid      double precision NOT NULL,
    fee_ask      double precision NOT NULL,
    created_at   timestamptz      NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS metrics (
    run_id        bigint           NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    period        text             NOT NULL CHECK (period IN ('test', 'forward')),
    period_start  date             NOT NULL,
    period_end    date             NOT NULL,
    total_return  double precision NOT NULL,
    sharpe        double precision,
    max_drawdown  double precision NOT NULL,
    trade_count   integer          NOT NULL,
    win_rate      double precision,
    PRIMARY KEY (run_id, period)
);

CREATE TABLE IF NOT EXISTS baselines (
    ticker                 text             NOT NULL,
    period                 text             NOT NULL CHECK (period IN ('test', 'forward')),
    period_start           date             NOT NULL,
    period_end             date             NOT NULL,
    fee_bid                double precision NOT NULL,
    fee_ask                double precision NOT NULL,
    buy_hold_return        double precision NOT NULL,
    buy_hold_sharpe        double precision,
    buy_hold_max_drawdown  double precision NOT NULL,
    PRIMARY KEY (ticker, period, period_start, period_end)
);

CREATE TABLE IF NOT EXISTS equity_curves (
    run_id  bigint           NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    period  text             NOT NULL CHECK (period IN ('test', 'forward')),
    date    date             NOT NULL,
    equity  double precision NOT NULL,
    PRIMARY KEY (run_id, period, date)
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id            bigserial   PRIMARY KEY,
    question      text        NOT NULL,
    model         text        NOT NULL,
    tools_called  jsonb       NOT NULL DEFAULT '[]',
    latency_ms    integer,
    grounded      boolean,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS runs_lookup_idx ON runs (ticker, algo, feature_set);
CREATE INDEX IF NOT EXISTS metrics_run_idx ON metrics (run_id);
