import type { Verdict } from "@/lib/strategies";
import { StatusBadge, type StatusTone } from "./StatusBadge";

export const VERDICT_LABELS: Record<Verdict, string> = {
  beats: "Beats buy-and-hold",
  trails: "Trails buy-and-hold",
  unclear: "No clear difference",
  "not-compared": "Not compared",
};

const VERDICT_TONES: Record<Verdict, StatusTone> = {
  beats: "good",
  trails: "critical",
  unclear: "neutral",
  "not-compared": "neutral",
};

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  return <StatusBadge tone={VERDICT_TONES[verdict]} label={VERDICT_LABELS[verdict]} />;
}
