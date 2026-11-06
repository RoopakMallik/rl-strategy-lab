"""Answer a question about the results with Qwen (via Ollama), using only the fixed tools.

The loop:
  1. Qwen sees the question and the tool definitions, and calls tools; we run them and feed back
     the rows (up to ASSISTANT_MAX_TOOL_ROUNDS rounds).
  2. Qwen writes its final answer as JSON matching AssistantAnswer (Ollama structured output).
  3. The grounding check compares every number and date in it with the tool output.
  4. If the check fails, Qwen gets one retry with the problems listed. If that fails too, the
     response carries the raw tool results instead (used_fallback=True).
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable, Protocol

from ollama import Client
from pydantic import ValidationError

from ..settings import AssistantSettings, load_settings
from .answer_schema import AssistantAnswer, AssistantResponse, GroundingResult, ToolCallRecord
from .grounding_check import check_grounding
from .result_queries import ASSISTANT_TOOLS, NoResultsError, ToolArgumentError, ToolExecutionError, run_tool

FALLBACK_ANSWER = ("I could not write a summary whose numbers all match the stored results, "
                   "so here are the raw results from the tools I called.")
GROUNDING_ATTEMPTS = 2  # the first answer plus one retry


class ChatClient(Protocol):
    def chat(self, **kwargs) -> Any: ...


def system_prompt() -> str:
    s = load_settings()
    w = s.windows
    return f"""You answer questions about the RL Strategy Lab results, stored in a database.
The lab trained {', '.join(s.training.algorithms)} trading agents (Buy/Sell/Hold, long-only) on {', '.join(s.market_data.tickers)},
with the feature sets {', '.join(s.training.feature_sets)} ('standard' is price and volume; 'indicators' adds SMA, RSI and OBV).
Each strategy (ticker + algorithm + feature set) was trained with several random seeds.
Training data: {w.train_start} to {w.train_end}. The 'test' period is {w.test_start} to {w.test_end}.
The 'forward' period is every trading day after {w.test_end}: performance since training.
Fees: {s.trading.buy_fee_rate:.2%} per buy and {s.trading.sell_fee_rate:.2%} per sell, for agents and buy-and-hold.

Rules:
- Always call a tool to get numbers. Never state a number from memory or general knowledge.
- Pass a ticker only if the question names one. Questions about "all tickers", "overall" or
  "across" tickers must not set a ticker.
- For rankings, the answer is the strategy with rank 1. Leave order out for "best"; use
  lowest_first or highest_first when the question asks for the lowest, highest or worst value.
- Copy numbers exactly as the tool returns them. Fields ending in _pct are already percentages.
- Do not calculate new numbers (no differences, averages or sums): every number you write must appear in a tool result.
- Write dates as YYYY-MM-DD.
- If the stored results cannot answer the question (other tickers or algorithms, future prices,
  investment advice), do not call more tools: say what the data covers and set answerable to false.
- Keep the answer short: two to four sentences."""


FINAL_ANSWER_INSTRUCTION = """Now write your final answer as JSON with these fields:
- answer: the short plain-English answer
- claims: one entry per number in the answer, each with metric (what it is), value (the number
  exactly as in the tool output) and source_tool (the tool that returned it)
- answerable: false only if the stored results cannot answer the question"""


class ResultsAssistant:
    def __init__(self, settings: AssistantSettings | None = None, chat_client: ChatClient | None = None,
                 tool_runner: Callable[[str, dict], Any] = run_tool, model: str | None = None):
        self.settings = settings or load_settings().assistant
        self.model = model or self.settings.model
        self.chat_client = chat_client or Client(host=self.settings.ollama_host,
                                                 timeout=self.settings.request_timeout_seconds)
        self.tool_runner = tool_runner
        self.tool_definitions = [tool.ollama_definition() for tool in ASSISTANT_TOOLS.values()]

    def answer(self, question: str) -> AssistantResponse:
        started = time.perf_counter()
        messages: list[Any] = [{"role": "system", "content": system_prompt()},
                               {"role": "user", "content": question}]
        tool_calls = self._gather_tool_results(messages)

        messages.append({"role": "user", "content": FINAL_ANSWER_INSTRUCTION})
        final: AssistantAnswer | None = None
        grounding = GroundingResult(passed=False, checks=[], problems=["no answer produced"])
        attempts = 0
        while attempts < GROUNDING_ATTEMPTS:
            attempts += 1
            reply = self._chat(messages, structured=True)
            messages.append({"role": "assistant", "content": reply.message.content or ""})
            try:
                final = AssistantAnswer.model_validate_json(reply.message.content or "")
            except ValidationError as exc:
                final = None
                grounding = GroundingResult(passed=False, checks=[], problems=[f"answer was not valid JSON: {exc.errors()[0]['msg']}"])
            else:
                grounding = check_grounding(final, tool_calls, question, self.settings.grounding_relative_tolerance)
                if grounding.passed:
                    break
            messages.append({"role": "user", "content": (
                "Your answer failed verification: " + "; ".join(grounding.problems) +
                ". Rewrite it using only numbers and dates that appear in the tool results, copied exactly. "
                "Leave out anything you cannot copy from them.")})

        used_fallback = not grounding.passed
        return AssistantResponse(
            question=question,
            answer=FALLBACK_ANSWER if used_fallback else final.answer,
            answerable=final.answerable if final else True,
            claims=[] if used_fallback else final.claims,
            tool_calls=tool_calls,
            grounding=grounding,
            attempts=attempts,
            used_fallback=used_fallback,
            unverified_answer=final.answer if used_fallback and final else None,
            model=self.model,
            latency_ms=round((time.perf_counter() - started) * 1000),
        )

    def _gather_tool_results(self, messages: list) -> list[ToolCallRecord]:
        records: list[ToolCallRecord] = []
        for _ in range(self.settings.max_tool_rounds):
            reply = self._chat(messages, structured=False)
            requested = reply.message.tool_calls or []
            if not requested:
                break
            messages.append(reply.message)
            for call in requested:
                record = self._run_tool(call.function.name, dict(call.function.arguments or {}))
                records.append(record)
                content = json.dumps(record.result) if record.error is None else json.dumps({"error": record.error})
                messages.append({"role": "tool", "tool_name": record.name, "content": content})
        return records

    def _run_tool(self, name: str, arguments: dict) -> ToolCallRecord:
        try:
            return ToolCallRecord(name=name, arguments=arguments, result=self.tool_runner(name, arguments))
        except (ToolArgumentError, NoResultsError, ToolExecutionError) as exc:
            return ToolCallRecord(name=name, arguments=arguments, error=str(exc))

    def _chat(self, messages: list, structured: bool):
        options = {"temperature": self.settings.temperature}
        if structured:
            return self.chat_client.chat(model=self.model, messages=messages, options=options, think=False,
                                         format=AssistantAnswer.model_json_schema())
        return self.chat_client.chat(model=self.model, messages=messages, options=options, think=False,
                                     tools=self.tool_definitions)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Ask the results assistant one question.")
    parser.add_argument("question")
    response = ResultsAssistant().answer(parser.parse_args().question)
    print(response.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
