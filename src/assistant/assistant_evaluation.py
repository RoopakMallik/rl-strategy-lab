"""Evaluate the assistant on evals/assistant_questions.json and write a dated report.

    python -m src.assistant.assistant_evaluation [--model qwen3:4b] [--only lookup-return,catalog]

Each question names the tool(s) that can answer it and SQL that computes the expected key figure
straight from the database. Measures (as in the build plan):
- tool_selection_accuracy: an expected tool was called (answerable questions)
- answer_correctness: every expected value appears in the answer (answerable questions)
- grounding_first_try_rate: every number matched tool output on the first attempt (all questions)
- grounding_pass_rate: passed after at most one retry, i.e. no raw-table fallback (all questions)
- unanswerable_handling: out-of-scope questions answered with answerable=false
- median and 90th-percentile latency
Every request is also logged in assistant_requests.
"""
from __future__ import annotations

import argparse
import json
import statistics
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from ..database import connect_as_reader
from ..settings import PROJECT_ROOT, load_settings
from .answer_schema import AssistantResponse
from .grounding_check import number_is_grounded, numbers_in_text
from .request_log import save_assistant_request
from .results_assistant import ResultsAssistant

QUESTIONS_PATH = PROJECT_ROOT / "evals" / "assistant_questions.json"


def load_questions(path: Path = QUESTIONS_PATH) -> list[dict]:
    return json.loads(path.read_text())


def expected_values(sql: str) -> list:
    with connect_as_reader() as conn:
        row = conn.execute(sql).fetchone()
    if row is None or any(v is None for v in row.values()):
        raise RuntimeError(f"expected_sql returned no value; are results stored? SQL: {sql}")
    return [float(v) if isinstance(v, Decimal) else v for v in row.values()]


def answer_contains(response: AssistantResponse, value, relative_tolerance: float) -> bool:
    """Numbers: some number in the answer is a rounding of `value`. Text: every word appears."""
    text = response.answer + " " + " ".join(str(c.value) for c in response.claims)
    if isinstance(value, (int, float)):
        return any(number_is_grounded(number, [float(value)], relative_tolerance) for number in numbers_in_text(text))
    return all(word.lower() in text.lower() for word in str(value).split())


def score_question(question: dict, response: AssistantResponse, relative_tolerance: float) -> dict:
    answerable = question.get("expected_answerable", True)
    tools_called = [c.name for c in response.tool_calls]
    result = {
        "id": question["id"], "category": question["category"], "question": question["question"],
        "answer": response.answer, "tools_called": tools_called, "attempts": response.attempts,
        "grounded_first_try": response.grounding.passed and response.attempts == 1,
        "grounded": response.grounding.passed, "used_fallback": response.used_fallback,
        "latency_ms": response.latency_ms, "grounding_problems": response.grounding.problems,
    }
    if answerable:
        expected = expected_values(question["expected_sql"])
        result["expected_values"] = [str(v) for v in expected]
        result["tool_correct"] = any(t in tools_called for t in question["expected_tools"])
        result["answer_correct"] = not response.used_fallback and all(
            answer_contains(response, v, relative_tolerance) for v in expected)
    else:
        result["handled_unanswerable"] = response.answerable is False
    return result


def summarize(results: list[dict]) -> dict:
    answerable = [r for r in results if "tool_correct" in r]
    unanswerable = [r for r in results if "handled_unanswerable" in r]
    latencies = sorted(r["latency_ms"] for r in results)

    def share(rows, key):
        return round(sum(bool(r[key]) for r in rows) / len(rows), 3) if rows else None

    return {
        "questions": len(results),
        "tool_selection_accuracy": share(answerable, "tool_correct"),
        "answer_correctness": share(answerable, "answer_correct"),
        "grounding_first_try_rate": share(results, "grounded_first_try"),
        "grounding_pass_rate": share(results, "grounded"),
        "fallback_rate": share(results, "used_fallback"),
        "unanswerable_handling": share(unanswerable, "handled_unanswerable"),
        "median_latency_ms": statistics.median(latencies) if latencies else None,
        "p90_latency_ms": latencies[int(0.9 * (len(latencies) - 1))] if latencies else None,
    }


def run_evaluation(model: str | None = None, only: set[str] | None = None) -> dict:
    settings = load_settings()
    assistant = ResultsAssistant(model=model)
    questions = [q for q in load_questions() if not only or q["id"] in only]
    results = []
    for number, question in enumerate(questions, start=1):
        response = assistant.answer(question["question"])
        save_assistant_request(response)
        result = score_question(question, response, settings.assistant.grounding_relative_tolerance)
        results.append(result)
        verdict = ("tool ok" if result.get("tool_correct") else "TOOL MISS") if "tool_correct" in result else \
                  ("declined ok" if result["handled_unanswerable"] else "DID NOT DECLINE")
        correct = "" if "answer_correct" not in result else ("  answer ok" if result["answer_correct"] else "  ANSWER WRONG")
        print(f"[{number}/{len(questions)}] {question['id']}: {verdict}{correct}, "
              f"grounded={result['grounded']} attempts={result['attempts']} {result['latency_ms']} ms", flush=True)
    return {"suite": "assistant", "model": assistant.model,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "summary": summarize(results), "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", help="Ollama model tag (default ASSISTANT_MODEL)")
    parser.add_argument("--only", help="comma-separated question ids")
    args = parser.parse_args()
    report = run_evaluation(args.model, set(args.only.split(",")) if args.only else None)
    reports_dir = load_settings().evaluation_reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)
    model_slug = report["model"].replace(":", "-").replace("/", "-")
    path = reports_dir / f"assistant_{model_slug}_{date.today().isoformat()}.json"
    if not args.only:
        path.write_text(json.dumps(report, indent=2, default=str))
        print(f"Report: {path.relative_to(PROJECT_ROOT)}")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
