import type { ReactNode } from "react";

export interface TooltipRow {
  key: ReactNode;
  value: string;
  label: string;
}

const MAX_WIDTH = 240;

/** One floating readout, beside the pointer, flipped to its left in the right half, kept inside the chart. */
export function ChartTooltip({ x, y, chartWidth, title, rows }: {
  x: number;
  y: number;
  chartWidth: number;
  title: string;
  rows: TooltipRow[];
}) {
  const width = Math.min(MAX_WIDTH, chartWidth);
  const preferredLeft = x > chartWidth / 2 ? x - 12 - width : x + 12;
  const left = Math.max(0, Math.min(preferredLeft, chartWidth - width));
  return (
    <div className="tooltip" role="status" style={{ left, top: y, width }}>
      <div className="tooltip-title">{title}</div>
      {rows.map((row, i) => (
        <div className="tooltip-row" key={i}>
          <span aria-hidden="true">{row.key}</span>
          <strong>{row.value}</strong>
          <span>{row.label}</span>
        </div>
      ))}
    </div>
  );
}
