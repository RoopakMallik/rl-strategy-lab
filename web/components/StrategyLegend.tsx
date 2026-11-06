import { isFilledFeatureSet } from "@/lib/strategies";
import { LineKey, StrategyMarker } from "./StrategyMarker";

/** Colour = algorithm, fill = feature set, dashed = buy-and-hold. */
export function StrategyLegend({ algorithms, featureSets, buyAndHoldLabel }: {
  algorithms: string[];
  featureSets: string[];
  buyAndHoldLabel?: string;
}) {
  const filled = featureSets.find(isFilledFeatureSet) ?? featureSets[0];
  return (
    <ul className="legend" aria-label="Legend">
      {algorithms.map((algorithm) => (
        <li key={algorithm}>
          <StrategyMarker algorithm={algorithm} featureSet={filled} algorithms={algorithms} />
          {algorithm}
        </li>
      ))}
      {featureSets.map((featureSet) => (
        <li key={featureSet}>
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
            <circle cx="6" cy="6" r="4.5" strokeWidth="2" stroke="var(--text-secondary)"
              fill={isFilledFeatureSet(featureSet) ? "var(--text-secondary)" : "var(--surface)"} />
          </svg>
          {isFilledFeatureSet(featureSet) ? "filled" : "hollow"} = {featureSet}
        </li>
      ))}
      {buyAndHoldLabel && (
        <li>
          <LineKey color="var(--baseline)" dashed />
          {buyAndHoldLabel}
        </li>
      )}
    </ul>
  );
}
