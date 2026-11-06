"""API routes, with the assistant and the request log replaced so no Ollama or database is needed."""
import pytest
from fastapi.testclient import TestClient

import src.api_server as api_server
from src.assistant.answer_schema import AssistantResponse, GroundingResult


class FakeAssistant:
    model = "fake-model"

    def answer(self, question):
        return AssistantResponse(question=question, answer="DQN had the lowest drawdown.", answerable=True,
                                 claims=[], tool_calls=[], grounding=GroundingResult(passed=True, checks=[], problems=[]),
                                 attempts=1, used_fallback=False, model=self.model, latency_ms=5)


class BrokenAssistant(FakeAssistant):
    def answer(self, question):
        raise ConnectionError("Ollama is not running")


@pytest.fixture
def logged(monkeypatch):
    calls = []
    monkeypatch.setattr(api_server, "save_assistant_request", lambda response: calls.append(("ok", response.question)))
    monkeypatch.setattr(api_server, "save_failed_request", lambda question, *rest: calls.append(("failed", question)))
    return calls


def client_with(assistant):
    api_server.app.dependency_overrides[api_server.get_assistant] = lambda: assistant
    return TestClient(api_server.app)


def test_docs_list_the_three_endpoints():
    paths = TestClient(api_server.app).get("/openapi.json").json()["paths"]
    assert {"/metrics", "/compare", "/ask"} <= set(paths)


def test_ask_returns_the_answer_and_logs_it(logged):
    response = client_with(FakeAssistant()).post("/ask", json={"question": "Lowest drawdown on NVDA?"})
    assert response.status_code == 200
    assert response.json()["answer"] == "DQN had the lowest drawdown."
    assert logged == [("ok", "Lowest drawdown on NVDA?")]


def test_ask_reports_an_unavailable_model_and_logs_the_failure(logged):
    response = client_with(BrokenAssistant()).post("/ask", json={"question": "Lowest drawdown on NVDA?"})
    assert response.status_code == 503
    assert logged == [("failed", "Lowest drawdown on NVDA?")]


def test_ask_rejects_an_empty_question(logged):
    assert client_with(FakeAssistant()).post("/ask", json={"question": ""}).status_code == 422


def test_metrics_rejects_an_unknown_algorithm():
    response = TestClient(api_server.app).get("/metrics", params={"ticker": "NVDA", "algorithm": "SAC",
                                                                   "feature_set": "standard"})
    assert response.status_code == 422
