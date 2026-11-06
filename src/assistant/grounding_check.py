"""Check that every number and date in an answer appears in the tool output it was based on.

Rules (pure functions, no model or database needed):
- Numbers are pulled from the answer text and from its claims. A number is grounded if some
  number in the tool results is within the rounding its written precision implies ("28.9"
  covers 28.85..28.95), plus GROUNDING_RELATIVE_TOLERANCE. Numbers are compared at face value:
  the tools already return percentages (fields ending in _pct), so "12.34%" must match 12.34.
- Signs: a number written with an explicit sign ("-4.26%", "+2.7%") must match the sign too.
  An unsigned number may match either sign, so "4.26% below" matches -4.26. A claim's value
  must match exactly, sign included.
- Dates (YYYY-MM-DD) must equal a date in the tool results. A bare year (1900-2100, no comma)
  must be the year of one.
- A claim's value may be a number, a date, or text (e.g. "false", "PPO", "AMD, INTC"); each
  listed text must equal a text or true/false value, ignoring case. Each claim is checked against
  the tool it cites.
- Not checked: whole numbers from 0 to 10 without decimals or %, which are counts and ranks
  ("3 tickers", "top 3"); numbers and dates that also appear in the question; and indicator
  periods written like SMA(12).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from .answer_schema import AssistantAnswer, Claim, GroundingResult, NumberCheck, ToolCallRecord

LARGEST_UNCHECKED_COUNT = 10
# A date may be followed by a time ("2026-11-05T12:56:07"), so no word boundary after it.
_DATE = re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)")
# A dash between two numbers is a range ("10-20%"), not a minus sign.
_RANGE_DASH = re.compile(r"(?<=\d)\s*[-–]\s*(?=\d)")
# Optional sign, digits (with thousands commas), decimals, optional %. Not preceded by a letter
# or dot (so "A2C" and "qwen3" are skipped); trailing letters are allowed ("3.5x").
_NUMBER = re.compile(r"(?<![\w.])([-+−])?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(\s?%)?(?!\d)")
_INDICATOR_PERIOD = re.compile(r"[A-Za-z]{2,}\(\d+\)")


@dataclass(frozen=True)
class WrittenNumber:
    text: str          # as written, e.g. "-4.26%"
    value: float       # signed value
    decimals: int
    has_percent: bool
    has_sign: bool
    has_thousands_separator: bool

    @property
    def is_count(self) -> bool:
        return (self.decimals == 0 and not self.has_percent and not self.has_sign
                and self.value <= LARGEST_UNCHECKED_COUNT)

    @property
    def looks_like_year(self) -> bool:
        return (self.decimals == 0 and not self.has_percent and not self.has_thousands_separator
                and 1900 <= self.value <= 2100)


@dataclass
class ToolValues:
    """Everything a grounded statement may quote from some tool calls."""
    numbers: list[float] = field(default_factory=list)
    dates: set[str] = field(default_factory=set)
    texts: set[str] = field(default_factory=set)   # lower-cased strings, and "true"/"false"

    @property
    def years(self) -> set[str]:
        return {d[:4] for d in self.dates}

    def add(self, value: Any) -> None:
        if value is None:
            return
        if isinstance(value, bool):
            self.texts.add(str(value).lower())
        elif isinstance(value, (int, float)):
            self.numbers.append(float(value))
        elif isinstance(value, str):
            self.texts.add(value.lower())
            self.dates.update(_DATE.findall(value))
        elif isinstance(value, dict):
            for item in value.values():
                self.add(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                self.add(item)


def collect_tool_values(tool_calls: Iterable[ToolCallRecord]) -> dict[str, ToolValues]:
    """Values per tool name, from the successful calls only."""
    by_tool: dict[str, ToolValues] = {}
    for call in tool_calls:
        if call.error is None:
            by_tool.setdefault(call.name, ToolValues()).add(call.result)
    return by_tool


def numbers_in_text(text: str) -> list[WrittenNumber]:
    """Every number written in `text`, outside dates and indicator labels such as SMA(12)."""
    cleaned = _RANGE_DASH.sub(" to ", _INDICATOR_PERIOD.sub(" ", _DATE.sub(" ", text)))
    found = []
    for match in _NUMBER.finditer(cleaned):
        sign, whole, fraction, percent = match.group(1), match.group(2), match.group(3) or "", match.group(4)
        value = float(whole.replace(",", "") + fraction) * (-1 if sign in ("-", "−") else 1)
        found.append(WrittenNumber(text=match.group(0).strip(), value=value, decimals=max(len(fraction) - 1, 0),
                                   has_percent=bool(percent), has_sign=bool(sign),
                                   has_thousands_separator="," in whole))
    return found


def number_is_grounded(number: WrittenNumber, tool_numbers: list[float], relative_tolerance: float) -> bool:
    """True if `number`, at its written precision, is a rounding of some tool number."""
    rounding = 0.5 * 10 ** -number.decimals
    for tool_value in tool_numbers:
        written, target = (number.value, tool_value) if number.has_sign else (abs(number.value), abs(tool_value))
        if abs(written - target) <= rounding + relative_tolerance * abs(target) + 1e-9:
            return True
    return False


def _claim_number(value: float) -> WrittenNumber:
    text = f"{value:g}"
    decimals = len(text.split(".")[1]) if "." in text else 0
    return WrittenNumber(text, value, decimals, False, True, False)  # claims must match sign exactly


def _claim_is_grounded(claim: Claim, tool: ToolValues, relative_tolerance: float) -> tuple[str, bool]:
    """(the value as written, grounded?) for one claim, against the output of its cited tool."""
    if not isinstance(claim.value, str):
        number = _claim_number(claim.value)
        return number.text, number_is_grounded(number, tool.numbers, relative_tolerance)
    written = claim.value.strip()
    if _DATE.fullmatch(written):
        return written, written in tool.dates
    numbers = numbers_in_text(written)
    if len(numbers) == 1 and numbers[0].text.replace(" ", "") == written.replace(" ", ""):
        number = WrittenNumber(written, numbers[0].value, numbers[0].decimals, False, True, False)
        return written, number_is_grounded(number, tool.numbers, relative_tolerance)
    items = [item.strip().lower() for item in re.split(r",|\band\b", written) if item.strip()]
    return written, bool(items) and all(item in tool.texts for item in items)  # "AMD, INTC and NVDA"


def check_grounding(answer: AssistantAnswer, tool_calls: list[ToolCallRecord], question: str,
                    relative_tolerance: float) -> GroundingResult:
    by_tool = collect_tool_values(tool_calls)
    every_tool = ToolValues()
    for call in tool_calls:
        if call.error is None:
            every_tool.add(call.result)
    question_numbers = {abs(n.value) for n in numbers_in_text(question)}
    question_dates = set(_DATE.findall(question))
    checks: list[NumberCheck] = []
    problems: list[str] = []

    for written in _DATE.findall(answer.answer):
        if written in question_dates:
            continue
        grounded = written in every_tool.dates
        checks.append(NumberCheck(text=written, grounded=grounded))
        if not grounded:
            problems.append(f"date {written} is not in the tool results")

    for number in numbers_in_text(answer.answer):
        if number.is_count or abs(number.value) in question_numbers:
            continue
        if number.looks_like_year:
            grounded = number.text in every_tool.years
        else:
            grounded = number_is_grounded(number, every_tool.numbers, relative_tolerance)
        checks.append(NumberCheck(text=number.text, grounded=grounded))
        if not grounded:
            problems.append(f"{number.text} is not in the tool results")

    for claim in answer.claims:
        cited = by_tool.get(claim.source_tool)
        if cited is None:
            written, grounded = str(claim.value), False
            problems.append(f"claim '{claim.metric}' cites {claim.source_tool!r}, which was not called successfully")
        else:
            written, grounded = _claim_is_grounded(claim, cited, relative_tolerance)
            if not grounded:
                problems.append(f"claim '{claim.metric}' = {written} is not in the output of {claim.source_tool}")
        checks.append(NumberCheck(text=f"{claim.metric}: {written}", grounded=grounded))

    return GroundingResult(passed=not problems, checks=checks, problems=problems)
