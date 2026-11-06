"""The grounding check catches made-up numbers and dates, and allows honest rounding."""
from src.assistant.answer_schema import AssistantAnswer, Claim, ToolCallRecord
from src.assistant.grounding_check import check_grounding

TOOL_CALLS = [ToolCallRecord(name="get_metrics", arguments={"ticker": "NVDA"}, result={
    "ticker": "NVDA", "period_start": "2025-01-02", "period_end": "2025-12-31", "seed_count": 5,
    "mean_total_return_pct": 28.87, "mean_max_drawdown_pct": 36.91, "mean_sharpe_ratio": 0.77,
    "excess_return_pct": -4.26, "beats_buy_and_hold": False,
})]
TOLERANCE = 0.001


def grounding(text: str, claims=(), question="How did PPO do on NVDA?"):
    return check_grounding(AssistantAnswer(answer=text, claims=list(claims)), TOOL_CALLS, question, TOLERANCE)


def test_exact_and_rounded_numbers_pass():
    result = grounding("PPO returned 28.87% (about 28.9%, or 29%) with a Sharpe ratio of 0.77, "
                       "from 2025-01-02 to 2025-12-31 in 2025.")
    assert result.passed, result.problems


def test_fabricated_number_is_caught():
    result = grounding("PPO returned 31.2% on NVDA.")
    assert not result.passed
    assert any("31.2%" in p for p in result.problems)


def test_fabricated_date_is_caught():
    result = grounding("The test period ended on 2025-11-30.")
    assert not result.passed


def test_fabricated_claim_is_caught_even_if_text_has_no_number():
    result = grounding("PPO did well.", [Claim(metric="return", value=45.0, source_tool="get_metrics")])
    assert not result.passed


def test_claim_must_cite_a_called_tool():
    result = grounding("PPO returned 28.87%.", [Claim(metric="return", value=28.87, source_tool="rank_strategies")])
    assert not result.passed


def test_unsigned_wording_may_describe_a_negative_value():
    assert grounding("It ended 4.26% below buy-and-hold.").passed


def test_an_explicit_sign_must_match():
    assert grounding("Excess return was -4.26%.").passed
    assert not grounding("PPO lost -28.87%.").passed       # the tool says +28.87
    assert not grounding("Excess return was +4.26%.").passed


def test_numbers_are_compared_at_face_value_not_scaled_by_100():
    assert not grounding("PPO returned 0.29%.").passed      # 28.87% / 100
    assert not grounding("PPO returned 2,887%.").passed     # 28.87% x 100
    assert not grounding("Mean return was 0.2887.").passed


def test_numbers_inside_ranges_and_with_units_are_checked():
    assert not grounding("Returns ranged 28.87-99.9%.").passed   # 99.9 is made up
    assert not grounding("That is 3.5x buy-and-hold.").passed    # 3.5 is made up


def test_thousands_are_not_mistaken_for_years():
    calls = [ToolCallRecord(name="get_metrics", arguments={}, result={"mean_trade_count": 2000.0})]
    answer = AssistantAnswer(answer="It made 2,000 trades.")
    assert check_grounding(answer, calls, "How many trades?", TOLERANCE).passed


def test_dates_repeated_from_the_question_are_not_checked():
    assert grounding("Since 2025-01-01 PPO returned 28.87%.", question="How did PPO do since 2025-01-01?").passed


def test_claims_are_checked_against_the_tool_they_cite():
    calls = TOOL_CALLS + [ToolCallRecord(name="data_freshness", arguments={}, result={"latest": "2026-11-04"})]
    answer = AssistantAnswer(answer="Return was 28.87%.",
                             claims=[Claim(metric="return", value=28.87, source_tool="data_freshness")])
    assert not check_grounding(answer, calls, "q", TOLERANCE).passed


def test_counts_labels_and_question_numbers_are_not_checked():
    result = grounding("Across 5 seeds and 3 tickers, the SMA(12) and RSI(14) features did not help; top 3 shown.",
                       question="Show the top 3 strategies")
    assert result.passed, result.problems


def test_rounding_is_bounded_by_written_precision():
    assert not grounding("PPO returned 28.7%.").passed     # 28.87 does not round to 28.7
    assert not grounding("Drawdown was 40%.").passed        # 36.91 does not round to 40


def test_failed_tool_calls_do_not_ground_anything():
    failed = [ToolCallRecord(name="get_metrics", arguments={}, error="No results for 28.87")]
    result = check_grounding(AssistantAnswer(answer="Return was 28.87%."), failed, "q", TOLERANCE)
    assert not result.passed


def test_dates_inside_timestamps_and_date_claims():
    calls = [ToolCallRecord(name="data_freshness", arguments={}, result={
        "latest_prices": [{"ticker": "NVDA", "latest_price_date": "2026-11-04"}],
        "last_price_refresh_at": "2026-11-05T12:56:07+00:00"})]
    answer = AssistantAnswer(answer="Prices run to 2026-11-04 and were refreshed on 2026-11-05.", claims=[
        Claim(metric="latest price date", value="2026-11-04", source_tool="data_freshness")])
    assert check_grounding(answer, calls, "How recent is the data?", TOLERANCE).passed
    wrong = AssistantAnswer(answer="Prices run to 2026-11-04.", claims=[
        Claim(metric="latest price date", value="2026-11-03", source_tool="data_freshness")])
    assert not check_grounding(wrong, calls, "How recent is the data?", TOLERANCE).passed


def test_claim_values_written_as_strings():
    """Qwen often writes claim values as JSON strings."""
    def claim(value):
        return [Claim(metric="m", value=value, source_tool="get_metrics")]
    assert grounding("PPO returned 28.87%.", claim("28.87")).passed
    assert grounding("PPO returned 28.87%.", claim("28.87%")).passed
    assert grounding("It did not beat buy-and-hold.", claim("false")).passed
    assert grounding("On NVDA.", claim("nvda")).passed
    assert not grounding("PPO returned 28.87%.", claim("31.5")).passed
    assert not grounding("It beat buy-and-hold.", claim("true")).passed


def test_text_claims_may_list_several_values():
    calls = [ToolCallRecord(name="list_strategies", arguments={}, result={
        "tickers": ["AMD", "INTC", "NVDA"], "algorithms": ["A2C", "DQN", "PPO"]})]
    def claim(value):
        return AssistantAnswer(answer="Covered.", claims=[Claim(metric="m", value=value, source_tool="list_strategies")])
    assert check_grounding(claim("AMD, INTC and NVDA"), calls, "q", TOLERANCE).passed
    assert not check_grounding(claim("A20C, DQN, PPO"), calls, "q", TOLERANCE).passed  # a misspelling is caught
