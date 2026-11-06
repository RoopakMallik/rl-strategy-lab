// Linear scales and round tick values for the inline SVG charts.

export function linearScale(domain: [number, number], range: [number, number]) {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const span = d1 - d0 || 1;
  return (value: number) => r0 + ((value - d0) / span) * (r1 - r0);
}

/** About `count` evenly spaced round values (1, 2, 2.5 or 5 x 10^n apart) covering min..max. */
export function niceTicks(min: number, max: number, count = 5): number[] {
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const rough = (max - min) / Math.max(count - 1, 1);
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= rough) ?? 10 * magnitude;
  const first = Math.floor(min / step) * step;
  const ticks: number[] = [];
  for (let tick = first; tick < max + step - 1e-9; tick += step) {
    ticks.push(Number(tick.toFixed(10)));
  }
  return ticks;
}

/** The decimals a tick label needs, from the spacing of the ticks: 0.25 apart -> 2. */
export function tickDecimals(ticks: number[]): number {
  if (ticks.length < 2) return 0;
  const step = Number(Math.abs(ticks[1] - ticks[0]).toFixed(10));
  return (String(step).split(".")[1] ?? "").length;
}
