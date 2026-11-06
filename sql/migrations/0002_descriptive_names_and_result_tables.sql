-- 0002: descriptive table and column names, plus the result tables the training grid,
-- forward test, strategy comparison and assistant write to.
--
-- prices and ingest_log hold data, so they are renamed in place. The original result tables
-- (runs, metrics, baselines, equity_curves, llm_calls) were never written to before this
-- migration, so they are replaced. The guard below stops the migration if any of them has rows.

DO $$
DECLARE
    table_name text;
    row_found boolean;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['runs', 'metrics', 'baselines', 'equity_curves', 'llm_calls'] LOOP
        IF to_regclass(table_name) IS NOT NULL THEN
            EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I)', table_name) INTO row_found;
            IF row_found THEN
                RAISE EXCEPTION 'Table % has rows; migrate them by hand before applying 0002', table_name;
            END IF;
        END IF;
    END LOOP;
END $$;

-- Market data: rename, keep the rows ------------------------------------------------------------
ALTER TABLE prices RENAME TO daily_prices;
ALTER TABLE daily_prices RENAME CONSTRAINT prices_pkey TO daily_prices_pkey;
ALTER TABLE daily_prices RENAME CONSTRAINT prices_check TO daily_prices_low_not_above_high;
ALTER TABLE daily_prices RENAME CONSTRAINT prices_low_check TO daily_prices_low_positive;
ALTER TABLE daily_prices RENAME CONSTRAINT prices_volume_check TO daily_prices_volume_not_negative;

ALTER TABLE ingest_log RENAME TO price_ingest_log;
ALTER SEQUENCE ingest_log_id_seq RENAME TO price_ingest_log_id_seq;
ALTER TABLE price_ingest_log RENAME CONSTRAINT ingest_log_pkey TO price_ingest_log_pkey;
ALTER TABLE price_ingest_log RENAME CONSTRAINT ingest_log_mode_check TO price_ingest_log_ingest_mode_check;
ALTER TABLE price_ingest_log RENAME COLUMN mode TO ingest_mode;
ALTER TABLE price_ingest_log RENAME COLUMN requested_from TO requested_from_date;
ALTER TABLE price_ingest_log RENAME COLUMN latest_date TO latest_price_date;
ALTER TABLE price_ingest_log RENAME COLUMN created_at TO ingested_at;

-- Replace the empty result tables ---------------------------------------------------------------
DROP TABLE IF EXISTS equity_curves, metrics, baselines, runs, llm_calls;

-- One trained agent. The UNIQUE key is its full configuration, so re-running the grid skips
-- agents that already exist instead of training duplicates.
CREATE TABLE training_runs (
    id                       bigserial        PRIMARY KEY,
    algorithm                text             NOT NULL CHECK (algorithm IN ('A2C', 'DQN', 'PPO')),
    feature_set              text             NOT NULL CHECK (feature_set IN ('standard', 'indicators')),
    ticker                   text             NOT NULL,
    seed                     integer          NOT NULL,
    train_start              date             NOT NULL,
    train_end                date             NOT NULL,
    test_start               date             NOT NULL,
    test_end                 date             NOT NULL,
    training_timesteps       integer          NOT NULL CHECK (training_timesteps > 0),
    observation_window_days  integer          NOT NULL CHECK (observation_window_days > 0),
    buy_fee_rate             double precision NOT NULL CHECK (buy_fee_rate >= 0),
    sell_fee_rate            double precision NOT NULL CHECK (sell_fee_rate >= 0),
    training_seconds         double precision NOT NULL,
    model_path               text             NOT NULL,
    created_at               timestamptz      NOT NULL DEFAULT now(),
    CONSTRAINT training_runs_train_before_test CHECK (train_end < test_start),
    CONSTRAINT training_runs_configuration_unique UNIQUE (
        algorithm, feature_set, ticker, seed, train_start, train_end, test_start, test_end,
        training_timesteps, observation_window_days, buy_fee_rate, sell_fee_rate)
);
CREATE INDEX training_runs_strategy_idx ON training_runs (ticker, algorithm, feature_set);

-- Performance of one run over one evaluation period. Returns and rates are fractions
-- (0.12 = 12%). max_drawdown is the largest peak-to-trough loss as a positive fraction.
CREATE TABLE run_metrics (
    run_id             bigint           NOT NULL REFERENCES training_runs (id) ON DELETE CASCADE,
    evaluation_period  text             NOT NULL CHECK (evaluation_period IN ('test', 'forward')),
    period_start       date             NOT NULL,
    period_end         date             NOT NULL,
    trading_days       integer          NOT NULL CHECK (trading_days > 0),
    total_return       double precision NOT NULL,
    sharpe_ratio       double precision,
    max_drawdown       double precision NOT NULL CHECK (max_drawdown BETWEEN 0 AND 1),
    trade_count        integer          NOT NULL CHECK (trade_count >= 0),
    round_trip_count   integer          NOT NULL CHECK (round_trip_count >= 0),
    win_rate           double precision CHECK (win_rate BETWEEN 0 AND 1),
    exposure           double precision NOT NULL CHECK (exposure BETWEEN 0 AND 1),
    evaluated_at       timestamptz      NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, evaluation_period)
);

-- Daily equity (starts at 1.0) of one run, for charts and the seed-averaged comparison.
CREATE TABLE run_equity_curves (
    run_id             bigint           NOT NULL REFERENCES training_runs (id) ON DELETE CASCADE,
    evaluation_period  text             NOT NULL CHECK (evaluation_period IN ('test', 'forward')),
    date               date             NOT NULL,
    equity             double precision NOT NULL,
    in_position        boolean          NOT NULL,
    PRIMARY KEY (run_id, evaluation_period, date)
);

-- Buy on the first day, sell on the last, same fees and days as the agents.
CREATE TABLE buy_and_hold_baselines (
    ticker             text             NOT NULL,
    evaluation_period  text             NOT NULL CHECK (evaluation_period IN ('test', 'forward')),
    period_start       date             NOT NULL,
    period_end         date             NOT NULL,
    trading_days       integer          NOT NULL CHECK (trading_days > 0),
    buy_fee_rate       double precision NOT NULL,
    sell_fee_rate      double precision NOT NULL,
    total_return       double precision NOT NULL,
    sharpe_ratio       double precision,
    max_drawdown       double precision NOT NULL CHECK (max_drawdown BETWEEN 0 AND 1),
    evaluated_at       timestamptz      NOT NULL DEFAULT now(),
    PRIMARY KEY (ticker, evaluation_period)
);

CREATE TABLE buy_and_hold_equity_curves (
    ticker             text             NOT NULL,
    evaluation_period  text             NOT NULL CHECK (evaluation_period IN ('test', 'forward')),
    date               date             NOT NULL,
    equity             double precision NOT NULL,
    PRIMARY KEY (ticker, evaluation_period, date)
);

-- One strategy (ticker + algorithm + feature set, all seeds) against buy-and-hold.
-- excess_return = (1 + seed-averaged strategy return) / (1 + buy-and-hold return) - 1.
-- The confidence interval is a moving-block bootstrap over the period's trading days.
CREATE TABLE strategy_baseline_comparisons (
    ticker                      text             NOT NULL,
    algorithm                   text             NOT NULL CHECK (algorithm IN ('A2C', 'DQN', 'PPO')),
    feature_set                 text             NOT NULL CHECK (feature_set IN ('standard', 'indicators')),
    evaluation_period           text             NOT NULL CHECK (evaluation_period IN ('test', 'forward')),
    period_start                date             NOT NULL,
    period_end                  date             NOT NULL,
    seed_count                  integer          NOT NULL CHECK (seed_count > 0),
    strategy_return             double precision NOT NULL,
    buy_and_hold_return         double precision NOT NULL,
    excess_return               double precision NOT NULL,
    excess_return_ci_low        double precision NOT NULL,
    excess_return_ci_high       double precision NOT NULL,
    confidence_level            double precision NOT NULL,
    seeds_beating_buy_and_hold  integer          NOT NULL,
    beats_buy_and_hold          boolean          NOT NULL,
    computed_at                 timestamptz      NOT NULL DEFAULT now(),
    PRIMARY KEY (ticker, algorithm, feature_set, evaluation_period)
);

-- One question put to the assistant, for latency and grounding statistics.
CREATE TABLE assistant_requests (
    id              bigserial   PRIMARY KEY,
    question        text        NOT NULL,
    model_name      text        NOT NULL,
    answer          text,
    tools_called    jsonb       NOT NULL DEFAULT '[]',
    attempts        integer     NOT NULL DEFAULT 0,
    grounded        boolean,
    used_fallback   boolean     NOT NULL DEFAULT false,
    latency_ms      integer,
    error           text,
    asked_at        timestamptz NOT NULL DEFAULT now()
);
