"""Record each question put to the assistant in `assistant_requests` (writer role).

The assistant itself only reads (read-only role); logging is a separate write by the caller.
"""
from __future__ import annotations

import json

from ..database import connect_as_writer
from .answer_schema import AssistantResponse


def save_assistant_request(response: AssistantResponse) -> None:
    with connect_as_writer() as conn:
        conn.execute(
            """INSERT INTO assistant_requests (question, model_name, answer, tools_called, attempts, grounded,
                   used_fallback, latency_ms)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (response.question, response.model, response.answer,
             json.dumps([{"name": c.name, "arguments": c.arguments, "error": c.error} for c in response.tool_calls]),
             response.attempts, response.grounding.passed, response.used_fallback, response.latency_ms),
        )


def save_failed_request(question: str, model: str, error: str, latency_ms: int) -> None:
    with connect_as_writer() as conn:
        conn.execute(
            "INSERT INTO assistant_requests (question, model_name, error, latency_ms) VALUES (%s, %s, %s, %s)",
            (question, model, error, latency_ms),
        )
