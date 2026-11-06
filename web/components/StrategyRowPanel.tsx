"use client";

import { type ReactNode, useState } from "react";
import { linearScale, niceTicks, tickDecimals } from "@/lib/scale";
import type { StrategyResult } from "@/lib/snapshotTypes";
import { algorithmColor, isFilledFeatureSet, strategyKey, strategyName } from "@/lib/strategies";
import { formatPercent } from "@/lib/format";
import { ChartTooltip, type TooltipRow } from "./ChartTooltip";

const LABEL_WIDTH = 128;
const ROW_HEIGHT = 30;
const MARGIN = { top: 22, right: 16, bottom: 28 };

export interface ReferenceLine {
  value: number;
  label: string;
  dashed: boolean;
}

/**
 * One ticker's panel: a row per strategy along a shared percent axis. Panels of the same chart get
 * the same `domain`, so they read on one scale. Each row is a hover and keyboard-focus target.
 */
export function StrategyRowPanel({ title, width, domain, strategies, algorithms, referenceLines, renderRow, tooltipFor }: {
  title: string;
  width: number;
  domain: [number, number];
  strategies: StrategyResult[];
  algorithms: string[];
  referenceLines: ReferenceLine[];
  renderRow: (strategy: StrategyResult, x: (value: number) => number, cy: number) => ReactNode;
  tooltipFor: (strategy: StrategyResult) => { anchor: number; rows: TooltipRow[] };
}) {
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const plotLeft = LABEL_WIDTH;
  const plotRight = Math.max(width - MARGIN.right, plotLeft + 80);
  const ticks = niceTicks(domain[0], domain[1], Math.max(3, Math.floor((plotRight - plotLeft) / 70)));
  const decimals = tickDecimals(ticks);
  const x = linearScale([ticks[0], ticks[ticks.length - 1]], [plotLeft, plotRight]);
  const height = MARGIN.top + strategies.length * ROW_HEIGHT + MARGIN.bottom;
  const rowCenter = (i: number) => MARGIN.top + i * ROW_HEIGHT + ROW_HEIGHT / 2;
  const axisY = height - MARGIN.bottom;

  const activeIndex = strategies.findIndex((s) => strategyKey(s) === activeKey);
  const active = activeIndex === -1 ? null : strategies[activeIndex];
  const tooltip = active ? tooltipFor(active) : null;

  return (
    <div>
      <h3 className="panel-title">{title}</h3>
      <div className="chart-frame">
        <svg width={width} height={height} role="group" aria-label={title}>
          {ticks.map((tick) => (
            <g key={tick}>
              <line x1={x(tick)} x2={x(tick)} y1={MARGIN.top} y2={axisY} stroke="var(--grid)" strokeWidth="1" />
              <text x={x(tick)} y={axisY + 18} textAnchor="middle" fontSize="12" fill="var(--text-muted)">
                {formatPercent(tick, { decimals })}
              </text>
            </g>
          ))}
          <line x1={plotLeft} x2={plotRight} y1={axisY} y2={axisY} stroke="var(--axis)" strokeWidth="1" />
          {active && (
            <rect x={0} y={rowCenter(activeIndex) - ROW_HEIGHT / 2} width={plotRight} height={ROW_HEIGHT} rx="4"
              fill="var(--surface-sunken)" />
          )}
          {referenceLines.map((line) => (
            <g key={line.label}>
              <line x1={x(line.value)} x2={x(line.value)} y1={MARGIN.top - 4} y2={axisY}
                stroke={line.dashed ? "var(--baseline)" : "var(--text-muted)"} strokeWidth={line.dashed ? 2 : 1}
                strokeDasharray={line.dashed ? "6 4" : undefined} />
              <text x={x(line.value)} y={MARGIN.top - 9} fontSize="12" fill="var(--text-secondary)"
                textAnchor={x(line.value) > (plotLeft + plotRight) / 2 ? "end" : "start"}>
                {line.label}
              </text>
            </g>
          ))}
          {strategies.map((s, i) => {
            const color = algorithmColor(s.algorithm, algorithms);
            const cy = rowCenter(i);
            const key = strategyKey(s);
            return (
              <g key={key} className="hit-target" tabIndex={0} role="img"
                aria-label={`${s.ticker} ${strategyName(s)}: ${tooltipFor(s).rows.map((r) => `${r.label} ${r.value}`).join(", ")}`}
                onPointerEnter={() => setActiveKey(key)} onPointerLeave={() => setActiveKey(null)}
                onFocus={() => setActiveKey(key)} onBlur={() => setActiveKey(null)}>
                <rect className="hit-area" x={0} y={cy - ROW_HEIGHT / 2} width={plotRight} height={ROW_HEIGHT} rx="4"
                  fill="transparent" />
                <circle cx={6} cy={cy} r="4.5" fill={isFilledFeatureSet(s.feature_set) ? color : "var(--surface)"}
                  stroke={color} strokeWidth="2" />
                <text x={18} y={cy} dy="0.32em" fontSize="12" fill="var(--text-secondary)">{strategyName(s)}</text>
                {renderRow(s, x, cy)}
              </g>
            );
          })}
        </svg>
        {active && tooltip && (
          <ChartTooltip x={x(tooltip.anchor)} y={rowCenter(activeIndex) + ROW_HEIGHT / 2} chartWidth={width}
            title={`${active.ticker} · ${strategyName(active)}`} rows={tooltip.rows} />
        )}
      </div>
    </div>
  );
}

/** A domain covering every value plus a little air on both sides. */
export function paddedDomain(values: number[]): [number, number] {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = (max - min || 1) * 0.04;
  return [min - pad, max + pad];
}
