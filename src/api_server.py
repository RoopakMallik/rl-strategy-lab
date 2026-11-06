"""HTTP API over the stored results and the assistant (FastAPI). Docs at /docs.

    python -m src.api_server        # serves on API_HOST:API_PORT

GET /metrics and GET /compare run the same validated read-only queries the assistant uses.
POST /ask runs the assistant and logs the request in `assistant_requests`.
"""
from __future__ import annotations

import time
from functools import lru_cache

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from .assistant.answer_schema import AssistantResponse
from .assistant.request_log import save_assistant_request, save_failed_request
from .assistant.result_queries import (Algorithm, BaselineComparison, CompareArguments, EvaluationPeriod, FeatureSet,
                                       NoResultsError, StrategyArguments, StrategyMetrics, ToolArgumentError,
                                       compare_to_baseline, get_metrics)
from .assistant.results_assistant import ResultsAssistant
from .settings import load_settings

app = FastAPI(title="RL Strategy Lab API",
              description="Results of A2C, DQN and PPO trading agents versus buy-and-hold, and a grounded "
                          "assistant that answers questions about them.")


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=500, examples=["Which strategy had the lowest drawdown on NVDA?"])


@lru_cache(maxsize=1)
def get_assistant() -> ResultsAssistant:
    return ResultsAssistant()


def _query(run, arguments_model, **arguments):
    try:
        return run(arguments_model.model_validate(arguments))
    except NoResultsError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except (ToolArgumentError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.get("/metrics", response_model=StrategyMetrics, summary="One strategy's metrics across seeds")
def metrics(ticker: str, algorithm: Algorithm, feature_set: FeatureSet, period: EvaluationPeriod = "test"):
    return _query(get_metrics, StrategyArguments, ticker=ticker, algorithm=algorithm,
                  feature_set=feature_set, period=period)


@app.get("/compare", response_model=list[BaselineComparison], summary="Strategies on one ticker vs buy-and-hold")
def compare(ticker: str, algorithm: Algorithm | None = None, feature_set: FeatureSet | None = None,
            period: EvaluationPeriod = Query("test")):
    return _query(compare_to_baseline, CompareArguments, ticker=ticker, algorithm=algorithm,
                  feature_set=feature_set, period=period)


@app.post("/ask", response_model=AssistantResponse, summary="Ask the grounded assistant a question")
def ask(body: Question, assistant: ResultsAssistant = Depends(get_assistant)):
    started = time.perf_counter()
    try:
        response = assistant.answer(body.question)
    except Exception as exc:  # Ollama down, model missing, timeout
        save_failed_request(body.question, assistant.model, f"{exc.__class__.__name__}: {exc}",
                            round((time.perf_counter() - started) * 1000))
        raise HTTPException(status_code=503, detail=f"The assistant is unavailable: {exc}") from None
    save_assistant_request(response)
    return response


@app.get("/health", summary="Liveness check")
def health():
    return {"status": "ok"}


def main() -> None:
    api = load_settings().api
    uvicorn.run(app, host=api.host, port=api.port)


if __name__ == "__main__":
    main()
