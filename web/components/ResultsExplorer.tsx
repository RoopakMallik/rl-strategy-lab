"use client";

import { useState } from "react";
import { formatDateRange, formatNumber } from "@/lib/format";
import type { BuyAndHoldBaseline, Configuration, EquityCurves, Period, StrategyResult } from "@/lib/snapshotTypes";
import { configuredOrder, PERIOD_LABELS } from "@/lib/strategies";
import { EquityCurveChart } from "./EquityCurveChart";
import { ExcessReturnChart } from "./ExcessReturnChart";
import { ResultsTable } from "./ResultsTable";
import { SeedReturnsChart } from "./SeedReturnsChart";
import { StrategyLegend } from "./StrategyLegend";

const ALL_TICKERS = "all";

/** One filter row (period, ticker) scoping the results table and every chart below it. */
export function ResultsExplorer({ strategies, baselines, equityCurves, configuration }: {
  strategies: StrategyResult[];
  baselines: BuyAndHoldBaseline[];
  equityCurves: EquityCurves;
  configuration: Configuration;
}) {
  const periods = (Object.keys(PERIOD_LABELS) as Period[]).filter((p) => strategies.some((s) => s.period === p));
  const [period, setPeriod] = useState<Period>(periods[0] ?? "test");
  const [ticker, setTicker] = useState<string>(ALL_TICKERS);

  const { algorithms, feature_sets: featureSets } = configuration;
  const tickers = ticker === ALL_TICKERS ? configuration.tickers : [ticker];
  const selected = strategies
    .filter((s) => s.period === period && tickers.includes(s.ticker))
    .sort(configuredOrder(configuration));
  const periodBaselines = baselines.filter((b) => b.period === period && tickers.includes(b.ticker));
  const tradingDays = periodBaselines.map((b) => b.trading_days);
  const periodWindow = periodBaselines[0];

  return (
    <>
      <div className="filters" role="group" aria-label="Filter results">
        <div className="filter-group">
          <span className="filter-label" id="period-filter">Period</span>
          <div className="segmented" role="group" aria-labelledby="period-filter">
            {periods.map((p) => (
              <button key={p} type="button" aria-pressed={p === period} onClick={() => setPeriod(p)}>
                {PERIOD_LABELS[p]}
              </button>
            ))}
          </div>
        </div>
        <div className="filter-group">
          <span className="filter-label" id="ticker-filter">Ticker</span>
          <div className="segmented" role="group" aria-labelledby="ticker-filter">
            {[ALL_TICKERS, ...configuration.tickers].map((t) => (
              <button key={t} type="button" aria-pressed={t === ticker} onClick={() => setTicker(t)}>
                {t === ALL_TICKERS ? "All" : t}
              </button>
            ))}
          </div>
        </div>
        {periodWindow && (
          <p className="small secondary">
            {formatDateRange(periodWindow.period_start, periodWindow.period_end)} · {formatNumber(Math.min(...tradingDays))}
            {Math.min(...tradingDays) === Math.max(...tradingDays) ? "" : `–${formatNumber(Math.max(...tradingDays))}`} trading days
          </p>
        )}
      </div>

      {period === "forward" && (
        <p className="notice">
          The forward period is every trading day since the test window ended, traded by the same agents,
          without retraining. It is a small sample: treat its numbers as an early read, not a result.
        </p>
      )}

      <section className="card" aria-labelledby="results-table-title">
        <div className="card-header">
          <h3 id="results-table-title">Results by strategy</h3>
          <p className="small secondary">
            A strategy is a ticker, an algorithm and a feature set, trained with {configuration.seeds.length} seeds.
          </p>
        </div>
        <ResultsTable strategies={selected} algorithms={algorithms} />
      </section>

      <section className="card" aria-labelledby="equity-title">
        <div className="card-header">
          <h3 id="equity-title">Growth of $1: strategy versus buy-and-hold</h3>
        </div>
        <EquityCurveChart strategies={selected} curves={equityCurves[period] ?? {}} algorithms={algorithms} />
      </section>

      <section className="card" aria-labelledby="excess-title">
        <div className="card-header">
          <h3 id="excess-title">Excess return over buy-and-hold, with {configuration.confidence_level_pct}% interval</h3>
          <p className="small secondary">
            Dot = excess return of the seed-averaged strategy; line = confidence interval. A strategy beats
            buy-and-hold only when its whole line sits right of zero.
          </p>
        </div>
        <StrategyLegend algorithms={algorithms} featureSets={featureSets} />
        <ExcessReturnChart strategies={selected} tickers={tickers} algorithms={algorithms} />
      </section>

      <section className="card" aria-labelledby="seeds-title">
        <div className="card-header">
          <h3 id="seeds-title">Return of every seed versus buy-and-hold</h3>
          <p className="small secondary">
            Each dot is one trained agent. Dots right of the dashed line ended above buy-and-hold.
          </p>
        </div>
        <StrategyLegend algorithms={algorithms} featureSets={featureSets} buyAndHoldLabel="Buy-and-hold return" />
        <SeedReturnsChart strategies={selected} tickers={tickers} algorithms={algorithms} />
      </section>
    </>
  );
}
