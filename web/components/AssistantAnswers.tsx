"use client";

import { useState } from "react";
import { formatDateTime, formatLatency } from "@/lib/format";
import type { AssistantAnswers as AssistantAnswersFile, AssistantResponse, ToolCall } from "@/lib/snapshotTypes";
import { StatusBadge } from "./StatusBadge";

function formatArguments(args: Record<string, unknown>): string {
  const entries = Object.entries(args);
  return entries.length === 0 ? "no arguments" : entries.map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ");
}

function ToolCallItem({ call, open }: { call: ToolCall; open: boolean }) {
  return (
    <li className="tool-call">
      <code>
        <strong>{call.name}</strong>({formatArguments(call.arguments)})
      </code>
      {call.error && <StatusBadge tone="critical" label={`Error: ${call.error}`} />}
      {call.result != null && (
        <details open={open}>
          <summary>Raw result</summary>
          <pre className="raw-json">{JSON.stringify(call.result, null, 2)}</pre>
        </details>
      )}
    </li>
  );
}

function Answer({ response }: { response: AssistantResponse }) {
  const { grounding } = response;
  return (
    <div className="answer card" aria-live="polite">
      <p className="answer-question">{response.question}</p>
      {response.used_fallback ? (
        <>
          <p className="notice">
            {response.answer} The model&apos;s answers did not pass the number check, so the tool results below
            are the answer.
          </p>
          {response.unverified_answer && (
            <div className="unverified-answer">
              <p className="unverified-label">Unverified: the model&apos;s last answer, rejected by the number check</p>
              <p>{response.unverified_answer}</p>
            </div>
          )}
        </>
      ) : (
        <p className="answer-text">{response.answer}</p>
      )}
      <div className="answer-meta">
        <StatusBadge tone={grounding.passed ? "good" : "critical"} label={grounding.passed ? "Grounded" : "Not grounded"} />
        <span>{response.attempts} {response.attempts === 1 ? "attempt" : "attempts"}</span>
        {!response.answerable && <StatusBadge tone="neutral" label="Marked unanswerable from the stored results" />}
        <span>{formatLatency(response.latency_ms)}</span>
      </div>

      <div>
        <h3 className="panel-title">
          {response.used_fallback ? "Number checks on the model's last, rejected answer" : "Number checks"}
        </h3>
        {grounding.checks.length === 0 ? (
          <p className="small muted">The answer states no numbers to check.</p>
        ) : (
          <ul className="checks" aria-label="Every number in the answer, checked against the tool output">
            {grounding.checks.map((check, i) => (
              <li key={i}>
                <StatusBadge tone={check.grounded ? "good" : "critical"} label={check.text} />
                <span className="muted">{check.grounded ? "found in tool output" : "not found"}</span>
              </li>
            ))}
          </ul>
        )}
        {grounding.problems.length > 0 && (
          <ul className="small secondary">
            {grounding.problems.map((problem, i) => <li key={i}>{problem}</li>)}
          </ul>
        )}
      </div>

      <div>
        <h3 className="panel-title">Database tools called</h3>
        {response.tool_calls.length === 0 ? (
          <p className="small muted">No tools were called.</p>
        ) : (
          <ul className="tool-calls">
            {response.tool_calls.map((call, i) => <ToolCallItem key={i} call={call} open={response.used_fallback} />)}
          </ul>
        )}
      </div>
    </div>
  );
}

/** The curated questions and the local model's pre-generated, number-checked answers. */
export function AssistantAnswers({ file }: { file: AssistantAnswersFile }) {
  const [selected, setSelected] = useState(0);
  if (file.answers.length === 0) return <p className="muted">No answers were exported.</p>;
  return (
    <>
      <p className="small secondary">
        Answers were pre-generated on {formatDateTime(file.generated_at)} by the local model <code>{file.model}</code>,
        which can only call six fixed, read-only database tools. Every number in an answer must appear in the
        tools&apos; output; if it does not after one retry, the raw tool results are returned instead.
      </p>
      <div className="assistant">
        <ul className="question-list" aria-label="Questions">
          {file.answers.map((response, i) => (
            <li key={i}>
              <button type="button" aria-pressed={i === selected} onClick={() => setSelected(i)}>
                {response.question}
              </button>
            </li>
          ))}
        </ul>
        <Answer response={file.answers[selected]} />
      </div>
    </>
  );
}
