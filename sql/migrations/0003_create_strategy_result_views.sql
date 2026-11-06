-- 0003: views that define "the current results" in one place, for the tools, API and notebook.

-- The newest run for each algorithm, feature set, ticker and seed. Older runs (for example from
-- a previous TRAIN_TIMESTEPS setting) stay in training_runs but drop out of every summary.
CREATE VIEW current_training_runs AS
SELECT DISTINCT ON (algorithm, feature_set, ticker, seed) *
FROM training_runs
ORDER BY algorithm, feature_set, ticker, seed, created_at DESC, id DESC;

-- One row per strategy and evaluation period: each metric's mean and spread across seeds.
CREATE VIEW strategy_results AS
SELECT
    r.ticker,
    r.algorithm,
    r.feature_set,
    m.evaluation_period,
    min(m.period_start)        AS period_start,
    max(m.period_end)          AS period_end,
    count(*)                   AS seed_count,
    avg(m.total_return)        AS mean_total_return,
    stddev_samp(m.total_return) AS stddev_total_return,
    min(m.total_return)        AS min_total_return,
    max(m.total_return)        AS max_total_return,
    avg(m.sharpe_ratio)        AS mean_sharpe_ratio,
    avg(m.max_drawdown)        AS mean_max_drawdown,
    avg(m.trade_count)         AS mean_trade_count,
    avg(m.win_rate)            AS mean_win_rate,
    avg(m.exposure)            AS mean_exposure
FROM current_training_runs r
JOIN run_metrics m ON m.run_id = r.id
GROUP BY r.ticker, r.algorithm, r.feature_set, m.evaluation_period;
