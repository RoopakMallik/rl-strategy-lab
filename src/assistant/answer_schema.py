"""The shapes the assistant produces: Qwen's structured answer, and the full response we return."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Claim(BaseModel):
    """One number the answer states, and the tool whose output contains it."""
    metric: str = Field(description="What the number is, e.g. 'mean test return of PPO indicators on NVDA'")
    value: float | str = Field(description="The number exactly as it appears in the tool output, a date as "
                                           "YYYY-MM-DD, or a text value such as true or false")
    source_tool: str = Field(description="Name of the tool whose output contains this number")


class AssistantAnswer(BaseModel):
    """What Qwen must return as JSON in its final message."""
    answer: str = Field(description="A short plain-English answer. Copy every number from the tool output.")
    claims: list[Claim] = Field(default_factory=list, description="Every number stated in the answer")
    answerable: bool = Field(True, description="False if the stored results cannot answer the question")


class ToolCallRecord(BaseModel):
    name: str
    arguments: dict[str, Any]
    result: Any | None = None
    error: str | None = None


class NumberCheck(BaseModel):
    text: str             # the number as written in the answer, e.g. "28.87%" or "2025-12-31"
    grounded: bool


class GroundingResult(BaseModel):
    passed: bool
    checks: list[NumberCheck]
    problems: list[str]   # human-readable reasons, fed back to the model on a retry


class AssistantResponse(BaseModel):
    question: str
    answer: str
    answerable: bool
    claims: list[Claim]
    tool_calls: list[ToolCallRecord]
    grounding: GroundingResult
    attempts: int
    used_fallback: bool = Field(description="True if no answer passed the grounding check; the tool results "
                                            "in tool_calls are then the answer")
    unverified_answer: str | None = Field(None, description="When used_fallback is true: the model's last answer, "
                                                            "which failed the grounding check. Context only.")
    model: str
    latency_ms: int
