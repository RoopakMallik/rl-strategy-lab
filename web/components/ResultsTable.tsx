"use client";

import { type ReactNode, useState } from "react";
import { formatNumber, formatPercent } from "@/lib/format";
import type { StrategyResult } from "@/lib/snapshotTypes";
import { strategyKey, strategyName, verdictOf } from "@/lib/strategies";
import { StrategyMarker } from "./StrategyMarker";
import { VerdictBadge } from "./VerdictBadge";

interface Column {
  id: string;
  label: string;
  /** The value sorted on; null sorts last. */
  sortValue: (s: StrategyResult) => number | string | null;
  render: (s: StrategyResult, algorithms: string[]) => ReactNode;
}

const VERDICT_RANK = { beats: 0, unclear: 1, trails: 2, "not-compared": 3 };

const COLUMNS: Column[] = [
  {
    id: "strategy", label: "Strategy", sortValue: () => null,
    render: (s, algorithms) => (
      <span className="strategy-cell">
        <StrategyMarker algorithm={s.algorithm} featureSet={s.feature_set} algorithms={algorithms} />
        <span><strong>{s.ticker}</strong> · {strategyName(s)}</span>
      </span>
    ),
  },
  {
    id: "return", label: "Mean return", sortValue: (s) => s.mean_total_return_pct,
    render: (s) => formatPercent(s.mean_total_return_pct, { signed: true }),
  },
  {
    id: "buy-and-hold", label: "Buy-and-hold", sortValue: (s) => s.buy_and_hold_return_pct,
    render: (s) => formatPercent(s.buy_and_hold_return_pct, { signed: true }),
  },
  {
    id: "excess", label: "Excess (CI)", sortValue: (s) => s.comparison?.excess_return_pct ?? null,
    render: (s) => s.comparison ? (
      <>
        {formatPercent(s.comparison.excess_return_pct, { signed: true })}{" "}
        <span className="ci">
          [{formatPercent(s.comparison.excess_return_ci_low_pct, { signed: true })},{" "}
          {formatPercent(s.comparison.excess_return_ci_high_pct, { signed: true })}]
        </span>
      </>
    ) : "–",
  },
  {
    id: "seeds", label: "Seeds beating", sortValue: (s) => s.comparison?.seeds_beating_buy_and_hold ?? null,
    render: (s) => s.comparison ? `${s.comparison.seeds_beating_buy_and_hold} of ${s.comparison.seed_count}` : "–",
  },
  {
    id: "sharpe", label: "Sharpe", sortValue: (s) => s.mean_sharpe_ratio,
    render: (s) => formatNumber(s.mean_sharpe_ratio, 2),
  },
  {
    id: "drawdown", label: "Max drawdown", sortValue: (s) => s.mean_max_drawdown_pct,
    render: (s) => formatPercent(s.mean_max_drawdown_pct),
  },
  {
    id: "trades", label: "Trades", sortValue: (s) => s.mean_trade_count,
    render: (s) => formatNumber(s.mean_trade_count, 1),
  },
  {
    id: "exposure", label: "Exposure", sortValue: (s) => s.mean_exposure_pct,
    render: (s) => formatPercent(s.mean_exposure_pct, { decimals: 0 }),
  },
  {
    id: "verdict", label: "Verdict", sortValue: (s) => VERDICT_RANK[verdictOf(s.comparison)],
    render: (s) => <VerdictBadge verdict={verdictOf(s.comparison)} />,
  },
];

type Sort = { column: string; descending: boolean } | null;

/** Every strategy in the selection. Click a column to sort; click again to reverse; the strategy column resets. */
export function ResultsTable({ strategies, algorithms }: { strategies: StrategyResult[]; algorithms: string[] }) {
  const [sort, setSort] = useState<Sort>(null);
  const column = COLUMNS.find((c) => c.id === sort?.column);
  const rows = column && sort ? [...strategies].sort((a, b) => {
    const va = column.sortValue(a);
    const vb = column.sortValue(b);
    if (va == null || vb == null) return va == null ? (vb == null ? 0 : 1) : -1;
    const order = va < vb ? -1 : va > vb ? 1 : 0;
    return sort.descending ? -order : order;
  }) : strategies;

  const toggle = (id: string) => {
    if (id === "strategy") return setSort(null);
    // Rank-like columns start ascending (best first); measures start with the largest value.
    const firstDescending = id !== "drawdown" && id !== "verdict";
    setSort(sort?.column === id ? { column: id, descending: !sort.descending } : { column: id, descending: firstDescending });
  };

  if (strategies.length === 0) return <p className="muted">No results for this selection.</p>;
  return (
    <div className="table-scroll">
      <table className="results-table" aria-describedby="results-table-caption">
        <thead>
          <tr>
            {COLUMNS.map((c) => {
              const sorted = sort?.column === c.id || (c.id === "strategy" && !sort);
              const direction = c.id === "strategy" ? "ascending" : sort?.descending ? "descending" : "ascending";
              return (
                <th key={c.id} scope="col" aria-sort={sorted ? direction : undefined}>
                  <button type="button" onClick={() => toggle(c.id)}>
                    {c.label}
                    <span className="sort-arrow" aria-hidden="true">
                      {sorted ? (direction === "descending" ? " ↓" : " ↑") : ""}
                    </span>
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={strategyKey(s)}>
              {COLUMNS.map((c) => <td key={c.id}>{c.render(s, algorithms)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="table-caption" id="results-table-caption">
        Means across seeds. Sorted by {column ? `“${column.label}”` : "ticker, algorithm and feature set"}.
      </p>
    </div>
  );
}
