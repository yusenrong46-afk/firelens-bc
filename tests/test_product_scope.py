"""FireLens is about wildfire in B.C.; unrelated first-turn questions get a scope note."""

from __future__ import annotations

import pytest

from firelens.answering.product_scope import is_outside_wildfire_scope
from firelens.contracts import QueryRequest


@pytest.mark.parametrize(
    "question",
    (
        "Who won the Stanley Cup?",
        "Write me a chocolate cake recipe.",
        "What is the capital of France?",
        "Tell me a joke.",
    ),
)
def test_unrelated_first_turn_questions_are_outside_scope(question: str) -> None:
    assert is_outside_wildfire_scope(QueryRequest(question=question))


@pytest.mark.parametrize(
    "question",
    (
        "Why do wildfires spread faster uphill?",
        "How do wildfires start?",
        "Why do some pine cones open after fire?",
        "What are controlled burns?",
        "What caused the 2023 BC wildfire season?",
        "Is the smoke bad in Kamloops?",
        "What is a fire weather index?",
        "Explain quantum entanglement then wildfire ranks.",
        "What can FireLens do?",
        "how many fires in bc",
    ),
)
def test_wildfire_and_bc_questions_stay_in_scope(question: str) -> None:
    assert not is_outside_wildfire_scope(QueryRequest(question=question))


def test_follow_ups_inherit_the_conversation_scope() -> None:
    request = QueryRequest(
        question="Why does that matter?",
        history=[
            {"role": "user", "content": "What belongs in a grab-and-go bag?"},
            {
                "role": "assistant",
                "content": "Reviewed guides list water, food, and documents.",
            },
        ],
    )
    assert not is_outside_wildfire_scope(request)
