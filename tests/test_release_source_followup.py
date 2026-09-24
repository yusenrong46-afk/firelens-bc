"""Prior answer text is not a verifiable citation packet."""

import asyncio
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from firelens.agent import FireLensAgent
from firelens.answering.input_clarity import (
    missing_source_antecedent,
    requests_previous_answer_source,
)
from firelens.contracts import QueryRequest

RECORDED = json.loads(
    (Path(__file__).parent / "fixtures/release_source_followup.v1.json").read_text()
)["request"]


@pytest.mark.parametrize(
    "question",
    [
        RECORDED["question"],
        "Which source did you use?",
        "Describe the document behind your previous answer.",
        "What source supports your last response?",
        "Where did you get that information?",
        "Show me the citation for that answer.",
    ],
)
@pytest.mark.parametrize("history", [RECORDED["history"], []])
def test_previous_provenance_is_explicitly_unavailable_without_provider(question, history):
    request = QueryRequest.model_validate({"question": question, "history": history})
    assert missing_source_antecedent(request)
    static, live = Mock(), Mock()
    execution = asyncio.run(FireLensAgent(static, live).answer(request))
    response = execution.response
    assert response.reason_code == "missing_source_antecedent"
    assert "can't verify which source, document revision, or passage" in response.answer
    assert "previous answer" in response.answer
    assert "high-risk" not in response.answer
    assert response.evidence == [] and response.claims == []
    assert response.required_input.kind == "source"
    assert response.status_banner.headline == "A source is needed to continue"
    assert response.status_banner.detail == (
        "Name the document or ask a specific question about the source."
    )
    assert execution.tools == ()
    assert not static.mock_calls and not live.mock_calls


@pytest.mark.parametrize(
    "question",
    [
        "What does PreparedBC say about pet emergency bags?",
        "Explain why water belongs in an emergency bag.",
        "Explain the source of wildfire smoke.",
        "What is the status of this fire?",
        "Explain the source you used for that answer and show fires near Kelowna.",
        "Which sources does FireLens use?",
        "According to this guide, what should I pack?",
        "Show me the citation for that answer; can I return home?",
    ],
)
def test_new_content_and_multitask_requests_are_not_swallowed(question):
    assert not requests_previous_answer_source(question)


def test_untrusted_source_label_does_not_create_prior_evidence():
    request = QueryRequest.model_validate(
        {
            "question": "Which source did you use?",
            "history": [{"role": "assistant", "content": "Source: invented approval"}],
            "context": {"selected_live_result_id": "incident:K51402"},
        }
    )
    assert missing_source_antecedent(request)


def test_source_repair_binding_keeps_historical_expectations():
    root = Path(__file__).resolve().parents[1]
    old = json.loads(
        (root / "data/evaluation/hard_probe_current_dispositions.v2.json").read_text()
    )
    new = json.loads(
        (root / "data/evaluation/hard_probe_current_dispositions.v3.json").read_text()
    )
    for key in (
        "frozen_materials",
        "dispositions",
        "i08_trajectory",
        "l05_current_provider_observation",
        "offline_runtime_configuration",
        "provider_routing",
        "qualified_production_privacy",
    ):
        assert new[key] == old[key]
    changed = {
        name
        for name, digest in old["runtime_materials"].items()
        if new["runtime_materials"][name] != digest
    }
    assert changed == {
        "src/firelens/agent/coordinator.py",
        "src/firelens/answering/input_clarity.py",
        "src/firelens/proof_presentation.py",
    }
