from firelens.source_requirements import SourceRequirement, source_requirement_for_question


def test_exact_guided_live_question_stays_in_live_lane() -> None:
    assert (
        source_requirement_for_question(
            "What official wildfire records are near Kelowna?", place_label="Kelowna"
        )
        == SourceRequirement.GENERAL_ALLOWED
    )


def test_explicit_reviewed_source_requires_reviewed_evidence() -> None:
    assert (
        source_requirement_for_question(
            "According to official guidance, what is wildfire rank?"
        )
        == SourceRequirement.REVIEWED_REQUIRED
    )
