"use client";

import { type KeyboardEvent, type PointerEvent, useState } from "react";
import { formatDate, formatEquity, formatMonth, formatPercent } from "@/lib/format";
import { linearScale, niceTicks, tickDecimals } from "@/lib/scale";
import type { EquityPoint, StrategyResult } from "@/lib/snapshotTypes";
import { algorithmColor, curveKey, isFilledFeatureSet, strategyKey, strategyName } from "@/lib/strategies";
import { useElementWidth } from "@/lib/useElementWidth";
import { ChartTooltip } from "./ChartTooltip";
import { LineKey, StrategyMarker } from "./StrategyMarker";

const HEIGHT = 300;
const MARGIN = { top: 12, right: 64, bottom: 28, left: 52 };
const MONTH_LABEL_WIDTH = 72;
const MIN_END_LABEL_GAP = 14;

/** Seed-averaged growth of $1 for one strategy, next to buy-and-hold on the same ticker. */
export function EquityCurveChart({ strategies, curves, algorithms }: {
  strategies: StrategyResult[];
  curves: Record<string, Record<string, EquityPoint[]>>;
  algorithms: string[];
}) {
  const [frameRef, width] = useElementWidth<HTMLDivElement>(720);
  const [chosenKey, setChosenKey] = useState<string | null>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const withCurves = strategies.filter((s) => (curves[s.ticker]?.[curveKey(s)] ?? []).length > 0);
  const bestByExcess = [...withCurves].sort(
    (a, b) => (b.comparison?.excess_return_pct ?? -Infinity) - (a.comparison?.excess_return_pct ?? -Infinity))[0];
  const selected = withCurves.find((s) => strategyKey(s) === chosenKey) ?? bestByExcess;
  if (!selected) return <p className="muted">No equity curves for this selection.</p>;

  const points = curves[selected.ticker][curveKey(selected)];
  const color = algorithmColor(selected.algorithm, algorithms);
  const filled = isFilledFeatureSet(selected.feature_set);

  const plotWidth = Math.max(width - MARGIN.left - MARGIN.right, 80);
  const values = points.flatMap(([, s, b]) => (b == null ? [s] : [s, b]));
  const yTicks = niceTicks(Math.min(...values), Math.max(...values), 5);
  const yDecimals = Math.max(tickDecimals(yTicks), 2);
  const x = linearScale([0, points.length - 1], [MARGIN.left, MARGIN.left + plotWidth]);
  const y = linearScale([yTicks[0], yTicks[yTicks.length - 1]], [HEIGHT - MARGIN.bottom, MARGIN.top]);

  const pathOf = (pick: (p: EquityPoint) => number | null) =>
    points.reduce((d, p, i) => {
      const v = pick(p);
      if (v == null) return d;
      return `${d}${d && pick(points[i - 1]) != null ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
    }, "");

  // Label the first trading day of a month, skipping months whose label would touch the previous one.
  const xTicks = points.reduce<number[]>((ticks, point, i) => {
    const monthStart = i === 0 || point[0].slice(0, 7) !== points[i - 1][0].slice(0, 7);
    const fits = ticks.length === 0 || x(i) - x(ticks[ticks.length - 1]) >= MONTH_LABEL_WIDTH;
    const fitsBeforeEnd = x(i) + MONTH_LABEL_WIDTH <= width;
    return monthStart && fits && fitsBeforeEnd ? [...ticks, i] : ticks;
  }, []);

  const last = points[points.length - 1];
  const endLabels = [{ value: last[1], key: "strategy" }, ...(last[2] == null ? [] : [{ value: last[2], key: "baseline" }])];
  const endLabelsCollide = endLabels.length === 2 && Math.abs(y(endLabels[0].value) - y(endLabels[1].value)) < MIN_END_LABEL_GAP;

  const indexAt = (event: PointerEvent<SVGSVGElement>) => {
    const left = event.currentTarget.getBoundingClientRect().left;
    const ratio = (event.clientX - left - MARGIN.left) / plotWidth;
    return Math.min(points.length - 1, Math.max(0, Math.round(ratio * (points.length - 1))));
  };
  const onKeyDown = (event: KeyboardEvent<SVGSVGElement>) => {
    const step = { ArrowLeft: -1, ArrowRight: 1, Home: -points.length, End: points.length }[event.key];
    if (step === undefined) return;
    event.preventDefault();
    setHoverIndex((i) => Math.min(points.length - 1, Math.max(0, (i ?? points.length - 1) + step)));
  };

  const hovered = hoverIndex == null ? null : points[Math.min(hoverIndex, points.length - 1)];
  const hoveredX = hovered ? x(points.indexOf(hovered)) : 0;
  const name = `${selected.ticker} ${strategyName(selected)}`;

  return (
    <div>
      <div className="chart-controls">
        <label className="filter-label" htmlFor="equity-strategy">Strategy</label>
        <select id="equity-strategy" value={strategyKey(selected)}
          onChange={(event) => { setChosenKey(event.target.value); setHoverIndex(null); }}>
          {withCurves.map((s) => (
            <option key={strategyKey(s)} value={strategyKey(s)}>
              {s.ticker} · {strategyName(s)}{s === bestByExcess ? " (highest excess return)" : ""}
            </option>
          ))}
        </select>
      </div>
      <ul className="legend" aria-label="Legend">
        <li>
          <LineKey color={color} />
          <StrategyMarker algorithm={selected.algorithm} featureSet={selected.feature_set} algorithms={algorithms} />
          {name}, mean of {selected.seed_count} seeds
        </li>
        <li>
          <LineKey color="var(--baseline)" dashed />
          {selected.ticker} buy-and-hold
        </li>
      </ul>
      <div className="chart-frame" ref={frameRef}>
        <svg width={width} height={HEIGHT} tabIndex={0} role="img"
          aria-label={`Growth of $1 for ${name} and buy-and-hold, ${formatDate(points[0][0])} to ${formatDate(last[0])}. ` +
            `Ends at ${formatEquity(last[1])} versus ${formatEquity(last[2])}. Use the arrow keys to read daily values.`}
          onPointerMove={(event) => setHoverIndex(indexAt(event))}
          onPointerLeave={() => setHoverIndex(null)}
          onFocus={() => setHoverIndex((i) => i ?? points.length - 1)}
          onBlur={() => setHoverIndex(null)}
          onKeyDown={onKeyDown}>
          {yTicks.map((tick) => (
            <g key={tick}>
              <line x1={MARGIN.left} x2={MARGIN.left + plotWidth} y1={y(tick)} y2={y(tick)} stroke="var(--grid)" strokeWidth="1" />
              <text x={MARGIN.left - 8} y={y(tick)} dy="0.32em" textAnchor="end" fontSize="12" fill="var(--text-muted)">
                ${tick.toFixed(yDecimals)}
              </text>
            </g>
          ))}
          <line x1={MARGIN.left} x2={MARGIN.left + plotWidth} y1={HEIGHT - MARGIN.bottom} y2={HEIGHT - MARGIN.bottom}
            stroke="var(--axis)" strokeWidth="1" />
          {xTicks.map((i) => (
            <text key={i} x={x(i)} y={HEIGHT - MARGIN.bottom + 18} textAnchor="start"
              fontSize="12" fill="var(--text-muted)">
              {formatMonth(points[i][0])}
            </text>
          ))}
          <path d={pathOf((p) => p[2])} fill="none" stroke="var(--baseline)" strokeWidth="2" strokeDasharray="6 4"
            strokeLinejoin="round" strokeLinecap="round" />
          <path d={pathOf((p) => p[1])} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
          <circle cx={x(points.length - 1)} cy={y(last[1])} r={filled ? 6 : 5} fill={filled ? color : "var(--surface)"}
            stroke={filled ? "var(--surface)" : color} strokeWidth="2" />
          {endLabels.filter((label) => !endLabelsCollide || label.key === "strategy").map((label) => (
            <text key={label.key} x={MARGIN.left + plotWidth + 10} y={y(label.value)} dy="0.32em" fontSize="12"
              fontWeight={label.key === "strategy" ? 600 : 400}
              fill={label.key === "strategy" ? "var(--text-primary)" : "var(--text-secondary)"}>
              {formatEquity(label.value)}
            </text>
          ))}
          {hovered && (
            <g pointerEvents="none">
              <line x1={hoveredX} x2={hoveredX} y1={MARGIN.top} y2={HEIGHT - MARGIN.bottom} stroke="var(--text-muted)" strokeWidth="1" />
              {hovered[2] != null && (
                <circle cx={hoveredX} cy={y(hovered[2])} r="4" fill="var(--baseline)" stroke="var(--surface)" strokeWidth="2" />
              )}
              <circle cx={hoveredX} cy={y(hovered[1])} r={filled ? 6 : 5} fill={filled ? color : "var(--surface)"}
                stroke={filled ? "var(--surface)" : color} strokeWidth="2" />
            </g>
          )}
        </svg>
        {hovered && (
          <ChartTooltip x={hoveredX} y={MARGIN.top} chartWidth={width} title={formatDate(hovered[0])}
            rows={[
              { key: <LineKey color={color} />, value: formatEquity(hovered[1]), label: strategyName(selected) },
              { key: <LineKey color="var(--baseline)" dashed />, value: formatEquity(hovered[2]), label: "Buy-and-hold" },
            ]} />
        )}
      </div>
      <p className="chart-note">
        Value of $1 invested on {formatDate(points[0][0])}, after fees. The strategy line is the mean of its seeds&apos;
        equity curves. Final: {formatEquity(last[1])} ({formatPercent(100 * (last[1] - 1), { signed: true })}) versus
        buy-and-hold {formatEquity(last[2])}{last[2] == null ? "" : ` (${formatPercent(100 * (last[2] - 1), { signed: true })})`}.
      </p>
    </div>
  );
}
