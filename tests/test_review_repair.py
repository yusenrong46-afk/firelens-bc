"""Unsealed repair regressions; public API plus admitted-corpus publication controls."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from firelens.contracts import QueryRequest
from firelens.evaluation.source_aware_conversation_runtime import fixture_agent
from firelens.guidance_capabilities import resolve_capability

F10 = "Harder: List every active fire in BC and tell me which ones threaten my house in West Kelowna."
# Independently transcribed from the fixed e2e upstream fixture, not its filtering code.
PROVINCE_IDS = {
    "incident:mountain",
    "incident:bear-creek",
    "incident:south-okanagan",
    "incident:kootenay",
}
F10_VARIANTS = [
    F10,
    F10.removeprefix("Harder: "),
    F10.replace("active fire", "active wildfire"),
    F10.replace("Harder: ", "Please "),
]


@pytest.mark.parametrize("question", F10_VARIANTS)
def test_province_mixed_public_path(question: str) -> None:
    from e2e_fixture_app import app

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/v1/ask", json={"question": question})
        assert response.status_code == 200
        body = response.json()
        print(json.dumps({"question": question, "response": body}))
        assert {row["result_id"] for row in body["live_results"]} == PROVINCE_IDS
        assert body["roster_total"] == 4
        sections = [s for s in body["answer_sections"] if s["kind"] == "safety_boundary"]
        assert sections and "cannot" in json.dumps(sections).lower()
        assert body["required_input"] is None

    asyncio.run(run())


@pytest.mark.parametrize(
    "question,expected",
    [
        ("Are there fires near me?", "requires_input"),
        ("Show fires in Alberta", "scope_redirect"),
        ("Should I evacuate?", "requires_input"),
        ("Fires near me and should I evacuate?", "requires_input"),
    ],
)
def test_public_boundary_controls(question: str, expected: str) -> None:
    from e2e_fixture_app import app

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/v1/ask", json={"question": question})
        body = response.json()
        assert body["response_mode"] == expected
        assert not body["live_results"]
        if "and should" in question:
            assert any(s["kind"] == "safety_boundary" for s in body["answer_sections"])

    asyncio.run(run())


GUIDANCE = [
    (
        "Who should I call when I am in danger during wildfire?",
        "immediate_danger_contact",
        "Do not call 911 unless",
    ),
    (
        "Who should I contact if I am in danger during a wildfire?",
        "immediate_danger_contact",
        "Do not call 911 unless",
    ),
    (
        "Who should I call when I am in immediate danger during wildfire?",
        "immediate_danger_contact",
        "Do not call 911 unless",
    ),
    (
        "What important documents should I put in my grab-and-go bag?",
        "documents_medications",
        "important documents",
    ),
    (
        "Which personal papers can we put in our emergency bag?",
        "documents_medications",
        "important documents",
    ),
    (
        "What documents and medicines should I have ready to evacuate?",
        "documents_medications",
        "important documents",
    ),
]


@pytest.mark.parametrize("question,capability,text", GUIDANCE)
def test_guidance_binding_publication(
    tmp_path: Path, question: str, capability: str, text: str
) -> None:
    async def run() -> None:
        agent, _, _ = await fixture_agent(tmp_path)
        execution = await agent.answer(QueryRequest(question=question))
        response = execution.response
        binding = resolve_capability(question)
        print(
            json.dumps(
                {
                    "question": question,
                    "binding": binding.model_dump(mode="json") if binding else None,
                    "response": response.model_dump(mode="json"),
                }
            )
        )
        assert binding is not None and binding.id == capability
        assert text in (response.answer or "")
        assert response.validation is not None and response.validation.accepted
        assert response.claims and response.evidence
        evidence = {e.evidence_id: e for e in response.evidence}
        for claim in response.claims:
            assert claim.publication is not None
            assert claim.publication.kind.value == "official_quote_only"
            for support in claim.supports:
                source = evidence[support.evidence_id]
                assert support.quote in source.primary_text
                expected_sources = {("PreparedBC", "page:6"), ("PreparedBC", "page:10")}
                if capability == "immediate_danger_contact":
                    expected_sources = {
                        (
                            "Province of British Columbia",
                            "section:if-you-receive-a-bc-emergency-alert",
                        ),
                        ("PreparedBC", "section:stay-safe-during-a-wildfire"),
                    }
                assert (source.publisher, source.locator) in expected_sources
        if capability == "immediate_danger_contact":
            assert "trapped and unable to evacuate" in (response.answer or "")
            assert "medical or safety emergency" in (response.answer or "")

    asyncio.run(run())


@pytest.mark.parametrize(
    "question",
    [
        "What important documents should I put in my mortgage application?",
        "According to Cedar Ridge, what important documents should I put in my grab-and-go bag?",
        "What important documents should I put in my grab-and-go bag according to Cedar Ridge?",
        "What important documents should I put in my grab-and-go bag and should I leave now?",
        "What does Cedar Ridge say about who to call when in danger during wildfire?",
        "Who should I call about fire insurance paperwork?",
    ],
)
def test_binding_negative_controls(question: str) -> None:
    assert resolve_capability(question) is None


@pytest.mark.parametrize(
    "question",
    [
        "What important documents should I put in my grab-and-go bag and should I leave now?",
        "Who should I call when I am in danger during wildfire and should I evacuate?",
    ],
)
def test_new_binding_does_not_absorb_personal_decision(tmp_path: Path, question: str) -> None:
    async def run() -> None:
        agent, _, _ = await fixture_agent(tmp_path)
        response = (await agent.answer(QueryRequest(question=question))).response
        print(json.dumps(response.model_dump(mode="json")))
        assert resolve_capability(question) is None
        assert (
            "important documents" in (response.answer or "")
            if "documents" in question
            else "Do not call 911 unless" in (response.answer or "")
        )
        assert response.claims and response.evidence
        assert (
            "cannot"
            in (
                (response.answer or "")
                + json.dumps(response.model_dump(mode="json").get("answer_sections", []))
            ).lower()
        )

    asyncio.run(run())
