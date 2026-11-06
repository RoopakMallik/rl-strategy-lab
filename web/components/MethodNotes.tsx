import { formatDateRange, formatList, formatNumber, formatPercent } from "@/lib/format";
import type { Configuration } from "@/lib/snapshotTypes";

export function MethodNotes({ configuration: c }: { configuration: Configuration }) {
  return (
    <dl className="method">
      <div>
        <dt>Agents</dt>
        <dd>
          {formatList(c.algorithms)} agents choose Buy, Sell or Hold each trading day, long-only and all-in. Each
          sees the last {c.observation_window_days} days of either standard features (price and volume) or
          indicators (adding moving average, RSI and on-balance volume), and trains for{" "}
          {formatNumber(c.training_timesteps)} steps per seed with {c.seeds.length} seeds per strategy.
        </dd>
      </div>
      <div>
        <dt>Windows</dt>
        <dd>
          Trained on {formatDateRange(c.train_start, c.train_end)}, tested on {formatDateRange(c.test_start, c.test_end)},
          which the agents never saw. The forward period is every trading day after the test window, traded by
          the same agents without retraining.
        </dd>
      </div>
      <div>
        <dt>Fees</dt>
        <dd>
          {formatPercent(c.buy_fee_pct, { decimals: 2 })} per buy and {formatPercent(c.sell_fee_pct, { decimals: 2 })} per
          sell, charged to the agents and to buy-and-hold alike. Holding a position costs nothing.
        </dd>
      </div>
      <div>
        <dt>Excess return</dt>
        <dd>
          The seeds of a strategy are treated as one equal-weight portfolio (the mean of their equity curves).
          Excess return = (1 + strategy return) ÷ (1 + buy-and-hold return) − 1: how much more money the strategy
          ended with than buying the stock on the first day and holding it.
        </dd>
      </div>
      <div>
        <dt>Beats buy-and-hold</dt>
        <dd>
          Only when the whole {c.confidence_level_pct}% confidence interval of the excess return lies above zero. The
          interval comes from a moving-block bootstrap ({formatNumber(c.bootstrap_samples)} resamples, blocks of{" "}
          {c.bootstrap_block_days} trading days) of the daily log-return difference over the period&apos;s trading
          days, so it reflects day-to-day market noise. The spread across seeds is shown separately, as
          seeds beating buy-and-hold and in the per-seed chart.
        </dd>
      </div>
      <div>
        <dt>Small samples</dt>
        <dd>
          One test year per ticker is a short history, and the forward period is shorter still: its numbers can
          swing a lot with a few more weeks of data.
        </dd>
      </div>
    </dl>
  );
}
