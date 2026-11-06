// Identity of a strategy (ticker + algorithm + feature set) and how it is drawn everywhere:
// the algorithm picks the categorical colour, the feature set picks filled or hollow marks.
import type { BaselineComparison, Configuration, Period, StrategyResult } from "./snapshotTypes";

export const PERIOD_LABELS: Record<Period, string> = {
  test: "Test period",
  forward: "Since training",
};

/** The feature set drawn with filled marks; every other feature set is hollow. */
const FILLED_FEATURE_SET = "indicators";

export function isFilledFeatureSet(featureSet: string): boolean {
  return featureSet === FILLED_FEATURE_SET;
}

/** Slot 1, 2, 3 ... of the categorical palette, by the algorithm's position in the configuration. */
export function algorithmColor(algorithm: string, algorithms: string[]): string {
  return `var(--series-${algorithms.indexOf(algorithm) + 1})`;
}

export function strategyKey(s: { ticker: string; algorithm: string; feature_set: string }): string {
  return `${s.ticker}|${s.algorithm}|${s.feature_set}`;
}

/** Key of a strategy's curve inside equity_curves.json[period][ticker]. */
export function curveKey(s: { algorithm: string; feature_set: string }): string {
  return `${s.algorithm}|${s.feature_set}`;
}

export function strategyName(s: { algorithm: string; feature_set: string }): string {
  return `${s.algorithm} · ${s.feature_set}`;
}

/** Fixed order everywhere: ticker, then algorithm, then feature set, as configured. */
export function configuredOrder(config: Configuration) {
  const rank = (list: string[], value: string) => {
    const index = list.indexOf(value);
    return index === -1 ? list.length : index;
  };
  return (a: StrategyResult, b: StrategyResult) =>
    rank(config.tickers, a.ticker) - rank(config.tickers, b.ticker) ||
    rank(config.algorithms, a.algorithm) - rank(config.algorithms, b.algorithm) ||
    rank(config.feature_sets, a.feature_set) - rank(config.feature_sets, b.feature_set);
}

export type Verdict = "beats" | "trails" | "unclear" | "not-compared";

/** "beats": the whole confidence interval of the excess return is above zero; "trails": below zero. */
export function verdictOf(comparison: BaselineComparison | null): Verdict {
  if (!comparison) return "not-compared";
  if (comparison.beats_buy_and_hold) return "beats";
  if (comparison.excess_return_ci_high_pct < 0) return "trails";
  return "unclear";
}
