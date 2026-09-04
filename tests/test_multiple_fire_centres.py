"""Multiple Fire Centre clarification must not silently pick one scope."""

from firelens.agent.query_plan import plan_agent_request
from firelens.contracts import QueryRequest
from firelens.live_support import official_fire_centres_from_question


def test_multiple_fire_centres_are_detected():
    centres = official_fire_centres_from_question(
        "What is happening within the Kamloops or Cariboo Fire Centre?"
    )
    assert centres == ("Kamloops Fire Centre", "Cariboo Fire Centre")


def test_multiple_fire_centres_require_clarification():
    plan = plan_agent_request(
        QueryRequest(question="What is happening within the Kamloops or Cariboo Fire Centre?")
    )
    assert plan.terminal_response is not None
    assert plan.terminal_response.response_mode.value == "requires_input"
    assert "Which Fire Centre should I use" in (plan.terminal_response.answer or "")
    assert "Kamloops" in (plan.terminal_response.answer or "")
    assert "Cariboo" in (plan.terminal_response.answer or "")


def test_single_fire_centre_still_resolves():
    centres = official_fire_centres_from_question(
        "What is happening in the Cariboo Fire Centre?"
    )
    assert centres == ("Cariboo Fire Centre",)
