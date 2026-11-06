import { formatDateTime, formatLatency, formatShare } from "@/lib/format";
import type { Dashboard } from "@/lib/snapshotTypes";
import { StatusBadge } from "./StatusBadge";

export function Evaluations({ evaluations }: { evaluations: Dashboard["evaluations"] }) {
  const { price_data: price, assistant } = evaluations;
  const measures = assistant && [
    { label: "Tool selection accuracy", value: formatShare(assistant.tool_selection_accuracy), hint: "an expected tool was called" },
    { label: "Answer correctness", value: formatShare(assistant.answer_correctness), hint: "the expected figure is in the answer" },
    { label: "Grounded on first try", value: formatShare(assistant.grounding_first_try_rate), hint: "every number matched tool output" },
    { label: "Grounding pass rate", value: formatShare(assistant.grounding_pass_rate), hint: "after at most one retry" },
    { label: "Unanswerable handled", value: formatShare(assistant.unanswerable_handling), hint: "out-of-scope questions declined" },
    { label: "Median latency", value: formatLatency(assistant.median_latency_ms), hint: `90th percentile ${formatLatency(assistant.p90_latency_ms)}` },
  ];
  return (
    <div className="chart-grid">
      <div className="card">
        <div className="card-header">
          <h3>Price data checks</h3>
          {price && <p className="small muted">Run {formatDateTime(price.generated_at)}</p>}
        </div>
        {price ? (
          <StatusBadge tone={price.passed === price.total ? "good" : "critical"}
            label={`${price.passed} of ${price.total} checks passed`} />
        ) : (
          <p className="muted">Not run yet.</p>
        )}
      </div>
      <div className="card">
        <div className="card-header">
          <h3>Assistant evaluation</h3>
          {assistant && (
            <p className="small muted">
              {assistant.questions} questions with answers computed straight from the database, model{" "}
              <code>{assistant.model}</code>, run {formatDateTime(assistant.generated_at)}
            </p>
          )}
        </div>
        {measures ? (
          <dl className="measures">
            {measures.map((m) => (
              <div key={m.label}>
                <dt>{m.label}</dt>
                <dd>
                  {m.value}
                  <span className="measure-hint">{m.hint}</span>
                </dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="muted">Not run yet.</p>
        )}
      </div>
    </div>
  );
}
