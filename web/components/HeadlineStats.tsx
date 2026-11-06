import { formatNumber, formatPercent } from "@/lib/format";
import type { Dashboard } from "@/lib/snapshotTypes";
import { strategyName, verdictOf } from "@/lib/strategies";
import { VerdictBadge } from "./VerdictBadge";

/** The answer in three numbers, from the test period, plus one line on the forward period. */
export function HeadlineStats({ dashboard }: { dashboard: Dashboard }) {
  const test = dashboard.summary.test;
  const forward = dashboard.summary.forward;
  const confidence = dashboard.configuration.confidence_level_pct;
  if (!test) return <p className="muted">No test-period results in this snapshot.</p>;

  const best = test.best_by_excess_return;
  const forwardDays = dashboard.baselines.find((b) => b.period === "forward")?.trading_days;
  return (
    <section className="section" aria-label="Headline results">
      <div className="tiles">
        <div className="card tile">
          <span className="tile-label">Strategies that beat buy-and-hold in the test period</span>
          <span className="tile-value">{test.beating_buy_and_hold} of {test.strategies}</span>
          <span className="tile-detail">
            {test.beating_buy_and_hold === 0
              ? `None of the ${test.strategies} strategies had an excess return whose ${confidence}% confidence interval lies fully above zero.`
              : `${test.beating_buy_and_hold === 1 ? "Its" : "Their"} excess return's ${confidence}% confidence interval lies fully above zero.`}
          </span>
        </div>
        <div className="card tile">
          <span className="tile-label">Individual seeds that ended above buy-and-hold</span>
          <span className="tile-value">{formatNumber(test.seeds_beating_buy_and_hold)} of {formatNumber(test.seeds)}</span>
          <span className="tile-detail">
            Each seed is one trained agent. Seeds are averaged per strategy before the confidence test.
          </span>
        </div>
        {best && (
          <div className="card tile">
            <span className="tile-label">
              {best.excess_return_pct >= 0 ? "Best excess return over buy-and-hold" : "Closest to buy-and-hold (best excess return)"}
            </span>
            <span className="tile-value">{formatPercent(best.excess_return_pct, { signed: true })}</span>
            <span className="tile-detail">
              {best.ticker} · {strategyName(best)}, {confidence}% interval{" "}
              {formatPercent(best.excess_return_ci_low_pct, { signed: true })} to{" "}
              {formatPercent(best.excess_return_ci_high_pct, { signed: true })}
            </span>
            <VerdictBadge verdict={verdictOf(best)} />
          </div>
        )}
      </div>
      {forward && (
        <p className="small secondary">
          Since training (forward period{forwardDays ? `, ${formatNumber(forwardDays)} trading days` : ""}):{" "}
          {forward.beating_buy_and_hold} of {forward.strategies} strategies beat buy-and-hold and{" "}
          {formatNumber(forward.seeds_beating_buy_and_hold)} of {formatNumber(forward.seeds)} seeds ended above it.
          A small sample.
        </p>
      )}
    </section>
  );
}
