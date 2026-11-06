// The shape of the JSON files written by src/dashboard_snapshot.py into public/data/.
// Fields ending in _pct are already percentages (12.34 means 12.34%). Dates are ISO strings;
// timestamps carry a time-zone offset.

export type Period = "test" | "forward";

export interface Configuration {
  tickers: string[];
  algorithms: string[];
  feature_sets: string[];
  seeds: number[];
  training_timesteps: number;
  observation_window_days: number;
  buy_fee_pct: number;
  sell_fee_pct: number;
  train_start: string;
  train_end: string;
  test_start: string;
  test_end: string;
  confidence_level_pct: number;
  bootstrap_samples: number;
  bootstrap_block_days: number;
  assistant_model: string;
}

export interface TickerFreshness {
  ticker: string;
  latest_price_date: string;
}

export interface TrainingWindow {
  train_start: string;
  train_end: string;
  test_start: string;
  test_end: string;
  agents: number;
  last_trained_at: string;
}

export interface DataFreshness {
  latest_prices: TickerFreshness[];
  last_price_refresh_at: string | null;
  training_windows: TrainingWindow[];
  forward_period_end: string | null;
}

/** StrategyMetrics in src/assistant/result_queries.py: means and spread across seeds. */
export interface StrategyMetrics {
  ticker: string;
  algorithm: string;
  feature_set: string;
  period: Period;
  period_start: string;
  period_end: string;
  seed_count: number;
  mean_total_return_pct: number;
  stddev_total_return_pct: number | null;
  min_total_return_pct: number;
  max_total_return_pct: number;
  mean_sharpe_ratio: number | null;
  mean_max_drawdown_pct: number;
  mean_trade_count: number;
  mean_win_rate_pct: number | null;
  mean_exposure_pct: number;
  buy_and_hold_return_pct: number | null;
}

/** BaselineComparison in src/assistant/result_queries.py. */
export interface BaselineComparison {
  ticker: string;
  algorithm: string;
  feature_set: string;
  period: Period;
  period_start: string;
  period_end: string;
  strategy_return_pct: number;
  buy_and_hold_return_pct: number;
  excess_return_pct: number;
  excess_return_ci_low_pct: number;
  excess_return_ci_high_pct: number;
  confidence_level_pct: number;
  seed_count: number;
  seeds_beating_buy_and_hold: number;
  beats_buy_and_hold: boolean;
}

export interface SeedReturn {
  seed: number;
  total_return_pct: number;
}

export interface StrategyResult extends StrategyMetrics {
  seed_returns: SeedReturn[];
  comparison: BaselineComparison | null;
}

export interface PeriodSummary {
  strategies: number;
  beating_buy_and_hold: number;
  seeds: number;
  seeds_beating_buy_and_hold: number;
  best_by_excess_return: BaselineComparison | null;
}

export interface BuyAndHoldBaseline {
  ticker: string;
  period: Period;
  period_start: string;
  period_end: string;
  trading_days: number;
  total_return_pct: number;
  sharpe_ratio: number | null;
  max_drawdown_pct: number;
}

export interface PriceDataEvaluation {
  generated_at: string;
  passed: number;
  total: number;
}

/** Rates are shares between 0 and 1; null when no question of that kind was asked. */
export interface AssistantEvaluation {
  generated_at: string;
  model: string;
  questions: number;
  tool_selection_accuracy: number | null;
  answer_correctness: number | null;
  grounding_first_try_rate: number | null;
  grounding_pass_rate: number | null;
  fallback_rate: number | null;
  unanswerable_handling: number | null;
  median_latency_ms: number | null;
  p90_latency_ms: number | null;
}

export interface Dashboard {
  generated_at: string;
  configuration: Configuration;
  freshness: DataFreshness;
  summary: Partial<Record<Period, PeriodSummary>>;
  baselines: BuyAndHoldBaseline[];
  strategies: StrategyResult[];
  evaluations: {
    price_data: PriceDataEvaluation | null;
    assistant: AssistantEvaluation | null;
  };
}

/** [date, seed-averaged strategy equity, buy-and-hold equity]; equity starts at 1.0. */
export type EquityPoint = [string, number, number | null];

/** period -> ticker -> "ALGORITHM|feature_set" -> daily points. */
export type EquityCurves = Partial<Record<Period, Record<string, Record<string, EquityPoint[]>>>>;

export interface ToolCall {
  name: string;
  arguments: Record<string, unknown>;
  result: unknown;
  error: string | null;
}

export interface NumberCheck {
  text: string;
  grounded: boolean;
}

export interface AssistantResponse {
  question: string;
  answer: string;
  answerable: boolean;
  claims: { metric: string; value: number | string; source_tool: string }[];
  tool_calls: ToolCall[];
  grounding: { passed: boolean; checks: NumberCheck[]; problems: string[] };
  attempts: number;
  used_fallback: boolean;
  /** The model's last answer, which failed the number check; set only when used_fallback is true. */
  unverified_answer: string | null;
  model: string;
  latency_ms: number;
}

export interface AssistantAnswers {
  generated_at: string;
  model: string;
  answers: AssistantResponse[];
}
