"use client";

import { formatPercent } from "@/lib/format";
import type { StrategyResult } from "@/lib/snapshotTypes";
import { algorithmColor, isFilledFeatureSet } from "@/lib/strategies";
import { useElementWidth } from "@/lib/useElementWidth";
import { StrategyMarker } from "./StrategyMarker";
import { paddedDomain, StrategyRowPanel } from "./StrategyRowPanel";

/** Every seed's return as a dot, against the ticker's buy-and-hold return (dashed line). */
export function SeedReturnsChart({ strategies, tickers, algorithms }: {
  strategies: StrategyResult[];
  tickers: string[];
  algorithms: string[];
}) {
  const [frameRef, width] = useElementWidth<HTMLDivElement>(720);
  const withSeeds = strategies.filter((s) => s.seed_returns.length > 0);
  if (withSeeds.length === 0) return <p className="muted">No per-seed returns for this selection.</p>;

  const domain = paddedDomain(withSeeds.flatMap((s) => [
    ...s.seed_returns.map((r) => r.total_return_pct),
    ...(s.buy_and_hold_return_pct == null ? [] : [s.buy_and_hold_return_pct]),
  ]));
  return (
    <div ref={frameRef} className="chart-grid">
      {tickers.map((ticker) => {
        const rows = withSeeds.filter((s) => s.ticker === ticker);
        const buyAndHold = rows.find((s) => s.buy_and_hold_return_pct != null)?.buy_and_hold_return_pct;
        return rows.length > 0 && (
          <StrategyRowPanel key={ticker} title={ticker} width={width} domain={domain} strategies={rows}
            algorithms={algorithms}
            referenceLines={buyAndHold == null ? [] :
              [{ value: buyAndHold, label: `Buy-and-hold ${formatPercent(buyAndHold, { signed: true })}`, dashed: true }]}
            renderRow={(s, x, cy) => {
              const color = algorithmColor(s.algorithm, algorithms);
              const filled = isFilledFeatureSet(s.feature_set);
              return s.seed_returns.map(({ seed, total_return_pct: value }) => (
                <circle key={seed} cx={x(value)} cy={cy} r={filled ? 5.5 : 4.5} fill={filled ? color : "var(--surface)"}
                  stroke={filled ? "var(--surface)" : color} strokeWidth="2" />
              ));
            }}
            tooltipFor={(s) => {
              const marker = <StrategyMarker algorithm={s.algorithm} featureSet={s.feature_set} algorithms={algorithms} />;
              return {
                anchor: s.mean_total_return_pct,
                rows: [
                  ...s.seed_returns.map(({ seed, total_return_pct: value }) => ({
                    key: marker, value: formatPercent(value, { signed: true }), label: `seed ${seed}`,
                  })),
                  { key: null, value: formatPercent(s.mean_total_return_pct, { signed: true }), label: "mean" },
                  { key: null, value: formatPercent(s.buy_and_hold_return_pct, { signed: true }), label: "buy-and-hold" },
                ],
              };
            }} />
        );
      })}
    </div>
  );
}
