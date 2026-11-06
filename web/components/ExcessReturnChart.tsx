"use client";

import { formatPercent } from "@/lib/format";
import type { StrategyResult } from "@/lib/snapshotTypes";
import { algorithmColor, isFilledFeatureSet, verdictOf } from "@/lib/strategies";
import { useElementWidth } from "@/lib/useElementWidth";
import { LineKey } from "./StrategyMarker";
import { paddedDomain, StrategyRowPanel } from "./StrategyRowPanel";
import { VERDICT_LABELS } from "./VerdictBadge";

/** Excess return over buy-and-hold with its bootstrap confidence interval, one panel per ticker. */
export function ExcessReturnChart({ strategies, tickers, algorithms }: {
  strategies: StrategyResult[];
  tickers: string[];
  algorithms: string[];
}) {
  const [frameRef, width] = useElementWidth<HTMLDivElement>(720);
  const compared = strategies.filter((s) => s.comparison);
  if (compared.length === 0) return <p className="muted">No buy-and-hold comparisons for this selection.</p>;

  const domain = paddedDomain([0, ...compared.flatMap((s) => [s.comparison!.excess_return_ci_low_pct, s.comparison!.excess_return_ci_high_pct])]);
  return (
    <div ref={frameRef} className="chart-grid">
      {tickers.map((ticker) => {
        const rows = compared.filter((s) => s.ticker === ticker);
        return rows.length > 0 && (
          <StrategyRowPanel key={ticker} title={ticker} width={width} domain={domain} strategies={rows}
            algorithms={algorithms}
            referenceLines={[{ value: 0, label: "Same as buy-and-hold", dashed: false }]}
            renderRow={(s, x, cy) => {
              const c = s.comparison!;
              const color = algorithmColor(s.algorithm, algorithms);
              const filled = isFilledFeatureSet(s.feature_set);
              return (
                <>
                  <line x1={x(c.excess_return_ci_low_pct)} x2={x(c.excess_return_ci_high_pct)} y1={cy} y2={cy}
                    stroke={color} strokeWidth="2" strokeLinecap="round" />
                  <circle cx={x(c.excess_return_pct)} cy={cy} r={filled ? 6 : 5} fill={filled ? color : "var(--surface)"}
                    stroke={filled ? "var(--surface)" : color} strokeWidth="2" />
                </>
              );
            }}
            tooltipFor={(s) => {
              const c = s.comparison!;
              const color = algorithmColor(s.algorithm, algorithms);
              return {
                anchor: c.excess_return_pct,
                rows: [
                  { key: <LineKey color={color} />, value: formatPercent(c.excess_return_pct, { signed: true }), label: "excess return" },
                  { key: null, value: `${formatPercent(c.excess_return_ci_low_pct, { signed: true })} to ${formatPercent(c.excess_return_ci_high_pct, { signed: true })}`,
                    label: `${c.confidence_level_pct}% interval` },
                  { key: null, value: VERDICT_LABELS[verdictOf(c)], label: "" },
                ],
              };
            }} />
        );
      })}
    </div>
  );
}
