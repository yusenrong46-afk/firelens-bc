from __future__ import annotations

import pytest

from firelens.guidance_capabilities import resolve_capability


@pytest.mark.parametrize(
    "question",
    (
        "Who should I call when I am in danger during a wildfire?",
        "Who do I contact if a wildfire puts me in immediate danger?",
        "Who should I call if I am trapped by a wildfire?",
        "Who should I contact if I cannot evacuate because of a wildfire?",
        "Who do I call for a medical emergency during a wildfire?",
    ),
)
def test_immediate_danger_contact_requires_an_emergency_condition(question: str) -> None:
    capability = resolve_capability(question)

    assert capability is not None
    assert capability.id == "immediate_danger_contact"


@pytest.mark.parametrize(
    "question",
    (
        "Who should I contact about the wildfire danger rating?",
        "Who should I call about wildfire danger in my area?",
        "What is the wildfire danger rating?",
        "Who should I contact about a fire near Kelowna?",
    ),
)
def test_non_emergency_contact_questions_do_not_inherit_the_911_quote_lane(
    question: str,
) -> None:
    assert resolve_capability(question) is None
