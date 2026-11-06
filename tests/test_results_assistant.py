"""The question loop with a scripted stand-in for Qwen: tool calls, retry, fallback."""
import json
from types import SimpleNamespace

import pytest

from src.assistant.result_queries import NoResultsError
from src.assistant.results_assistant import FALLBACK_ANSWER, ResultsAssistant
from src.settings import AssistantSettings

SETTINGS = AssistantSettings(ollama_host="unused", model="fake-model", temperature=0.0, max_tool_rounds=3,
                             request_timeout_seconds=1, grounding_relative_tolerance=0.001, equity_curve_max_points=30)
METRICS = {"ticker": "NVDA", "mean_max_drawdown_pct": 12.5, "algorithm": "DQN"}


def tool_call(name, arguments):
    return SimpleNamespace(function=SimpleNamespace(name=name, arguments=arguments))


def reply(content="", tool_calls=None):
    return SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls, role="assistant"))


def final(answer, claims=()):
    return reply(json.dumps({"answer": answer, "claims": list(claims), "answerable": True}))


class ScriptedChat:
    """Returns the scripted replies in order and records what it was asked."""
    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def chat(self, **kwargs):
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})  # copy: the list keeps growing
        return self.replies.pop(0)


class RecordingTools:
    def __init__(self, result=METRICS, error=None):
        self.calls, self.result, self.error = [], result, error

    def __call__(self, name, arguments):
        self.calls.append((name, arguments))
        if self.error:
            raise self.error
        return self.result


def make_assistant(chat, tools=None):
    return ResultsAssistant(settings=SETTINGS, chat_client=chat, tool_runner=tools or RecordingTools())


def test_tool_call_then_grounded_answer():
    tools = RecordingTools()
    chat = ScriptedChat(
        reply(tool_calls=[tool_call("rank_strategies", {"metric": "max_drawdown", "ticker": "NVDA"})]),
        reply("DQN had the lowest drawdown."),
        final("DQN had the lowest drawdown on NVDA, 12.5%.",
              [{"metric": "drawdown", "value": 12.5, "source_tool": "rank_strategies"}]),
    )
    response = make_assistant(chat, tools).answer("Which strategy had the lowest drawdown on NVDA?")
    assert tools.calls == [("rank_strategies", {"metric": "max_drawdown", "ticker": "NVDA"})]
    assert response.grounding.passed and not response.used_fallback and response.attempts == 1
    assert response.answer.startswith("DQN")
    assert "tools" in chat.requests[0] and "format" in chat.requests[-1]


def test_fabricated_number_gets_one_retry_then_passes():
    chat = ScriptedChat(
        reply(tool_calls=[tool_call("get_metrics", {})]),
        reply("done"),
        final("Drawdown was 9.9%."),
        final("Drawdown was 12.5%."),
    )
    response = make_assistant(chat).answer("What was the drawdown?")
    assert response.attempts == 2 and response.grounding.passed and not response.used_fallback
    retry_prompt = chat.requests[-1]["messages"][-1]["content"]
    assert "9.9%" in retry_prompt


def test_two_failures_fall_back_to_raw_tool_results():
    chat = ScriptedChat(
        reply(tool_calls=[tool_call("get_metrics", {})]),
        reply("done"),
        final("Drawdown was 9.9%."),
        final("Drawdown was 8.8%."),
    )
    response = make_assistant(chat).answer("What was the drawdown?")
    assert response.used_fallback and response.answer == FALLBACK_ANSWER
    assert response.tool_calls[0].result == METRICS and response.claims == []


def test_invalid_json_counts_as_a_failed_attempt():
    chat = ScriptedChat(reply("no tools"), reply("not json"), final("Nothing to report."))
    response = make_assistant(chat).answer("Hello?")
    assert response.attempts == 2 and response.grounding.passed


def test_tool_errors_are_returned_to_the_model_not_raised():
    tools = RecordingTools(error=NoResultsError("No forward results yet."))
    chat = ScriptedChat(reply(tool_calls=[tool_call("get_metrics", {})]), reply("none"),
                        final("There are no forward results yet."))
    response = make_assistant(chat, tools).answer("Forward results?")
    assert response.tool_calls[0].error == "No forward results yet."
    tool_message = chat.requests[1]["messages"][-1]
    assert tool_message["role"] == "tool" and "No forward results yet." in tool_message["content"]


def test_tool_rounds_are_capped():
    looping = [reply(tool_calls=[tool_call("data_freshness", {})]) for _ in range(SETTINGS.max_tool_rounds)]
    chat = ScriptedChat(*looping, final("Prices end soon."))
    response = make_assistant(chat).answer("How fresh is the data?")
    assert len(response.tool_calls) == SETTINGS.max_tool_rounds


@pytest.mark.parametrize("name", ["list_strategies", "get_metrics", "compare_to_baseline",
                                  "rank_strategies", "get_equity_curve", "data_freshness"])
def test_every_tool_is_offered_to_the_model(name):
    chat = ScriptedChat(reply("none"), final("ok"))
    make_assistant(chat).answer("q")
    assert name in {tool["function"]["name"] for tool in chat.requests[0]["tools"]}
