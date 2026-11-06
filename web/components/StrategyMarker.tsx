import { algorithmColor, isFilledFeatureSet } from "@/lib/strategies";

/** The dot that identifies a strategy: algorithm colour, filled for indicators, hollow for standard. */
export function StrategyMarker({ algorithm, featureSet, algorithms }: {
  algorithm: string;
  featureSet: string;
  algorithms: string[];
}) {
  const color = algorithmColor(algorithm, algorithms);
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" style={{ flex: "none" }}>
      <circle cx="6" cy="6" r="4.5" fill={isFilledFeatureSet(featureSet) ? color : "var(--surface)"}
        stroke={color} strokeWidth="2" />
    </svg>
  );
}

/** A short stroke that keys a line series in legends and tooltips. */
export function LineKey({ color, dashed = false }: { color: string; dashed?: boolean }) {
  return (
    <svg width="18" height="10" viewBox="0 0 18 10" aria-hidden="true" style={{ flex: "none" }}>
      <line x1="1" y1="5" x2="17" y2="5" stroke={color} strokeWidth="2" strokeLinecap="round"
        strokeDasharray={dashed ? "4 3" : undefined} />
    </svg>
  );
}
