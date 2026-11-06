// A status is never colour alone: a coloured icon plus a written label.

export type StatusTone = "good" | "critical" | "neutral";

const ICONS: Record<StatusTone, string> = { good: "✓", critical: "✕", neutral: "–" };

export function StatusBadge({ tone, label }: { tone: StatusTone; label: string }) {
  return (
    <span className={`status status-${tone}`}>
      <span className="status-icon" aria-hidden="true">
        {ICONS[tone]}
      </span>
      {label}
    </span>
  );
}
