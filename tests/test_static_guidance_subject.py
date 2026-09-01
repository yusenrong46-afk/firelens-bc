"""Focused edited-guidance retrieval-subject regressions."""

from firelens.answering.static_guidance_subject import (
    StaticGuidanceSubject,
    static_guidance_retrieval_query,
    static_guidance_subject,
)


def test_pet_evacuation_wording_targets_pet_grab_and_go_guidance() -> None:
    question = "What should be included for pets when evacuating a wildfire?"

    assert static_guidance_subject(question) == StaticGuidanceSubject.PET_GRAB_AND_GO
    assert (
        static_guidance_retrieval_query(question)
        == "pets emergency kit grab-and-go bag food water leashes carriers"
    )


def test_n95_wildfire_smoke_wording_targets_respirator_guidance() -> None:
    question = "Are N95 respirators useful when wildfire smoke is present?"

    assert static_guidance_subject(question) == StaticGuidanceSubject.WILDFIRE_SMOKE
    assert static_guidance_retrieval_query(question) == "N95 respirators wildfire smoke"
