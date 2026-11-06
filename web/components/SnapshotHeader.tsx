import { formatDate, formatDateRange, formatDateTime, formatList, formatNumber, formatPercent } from "@/lib/format";
import type { Dashboard } from "@/lib/snapshotTypes";

function latestPrices(dashboard: Dashboard): string {
  const prices = dashboard.freshness.latest_prices;
  const dates = new Set(prices.map((p) => p.latest_price_date));
  if (dates.size === 1) return formatDate(prices[0].latest_price_date);
  return prices.map((p) => `${p.ticker} ${formatDate(p.latest_price_date)}`).join(", ");
}

export function SnapshotHeader({ dashboard }: { dashboard: Dashboard }) {
  const { configuration: config, freshness } = dashboard;
  const windows = freshness.training_windows;
  const agents = windows.reduce((total, w) => total + w.agents, 0);
  return (
    <header className="header">
      <h1>RL Strategy Lab</h1>
      <p className="header-lede">
        Can reinforcement-learning trading agents beat simply buying and holding? {formatList(config.algorithms)} agents
        were trained on {formatList(config.tickers)} and tested on a later, held-out period against buy-and-hold,
        under the same fees.
      </p>
      <p className="snapshot-label">
        <span>Snapshot of the live system, generated on {formatDateTime(dashboard.generated_at)}</span>
      </p>
      <dl className="facts">
        <div>
          <dt>Training window</dt>
          <dd>{windows.length > 0
            ? windows.map((w) => formatDateRange(w.train_start, w.train_end)).join("; ")
            : formatDateRange(config.train_start, config.train_end)}</dd>
        </div>
        <div>
          <dt>Test window (held out)</dt>
          <dd>{windows.length > 0
            ? windows.map((w) => formatDateRange(w.test_start, w.test_end)).join("; ")
            : formatDateRange(config.test_start, config.test_end)}</dd>
        </div>
        <div>
          <dt>Latest price data</dt>
          <dd>{latestPrices(dashboard)}</dd>
        </div>
        <div>
          <dt>Forward period runs to</dt>
          <dd>{formatDate(freshness.forward_period_end)}</dd>
        </div>
        <div>
          <dt>Agents trained</dt>
          <dd>
            {formatNumber(agents)} ({config.tickers.length} tickers × {config.algorithms.length} algorithms ×{" "}
            {config.feature_sets.length} feature sets × {config.seeds.length} seeds)
          </dd>
        </div>
        <div>
          <dt>Fees</dt>
          <dd>{formatPercent(config.buy_fee_pct, { decimals: 2 })} per buy, {formatPercent(config.sell_fee_pct, { decimals: 2 })} per sell</dd>
        </div>
      </dl>
    </header>
  );
}
