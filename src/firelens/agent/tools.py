"""The fixed Ask tool vocabulary; no model-defined tools are allowed."""

from enum import StrEnum


class AgentTool(StrEnum):
    LIST_OFFICIAL_FIRES = "list_official_fires"
    GET_OFFICIAL_FIRE = "get_official_fire"
    LIST_OFFICIAL_EVACUATIONS = "list_official_evacuations"
    SEARCH_REVIEWED_GUIDANCE = "search_reviewed_guidance"
    # Legacy aliases used by older V3 tests and tool-attribution helpers.
    LIST_ACTIVE_FIRES = "list_official_fires"
    GET_FIRE_DETAILS = "get_official_fire"
    GET_EVACUATION_INFORMATION = "list_official_evacuations"
    ANSWER_GENERAL_BACKGROUND = "answer_general_background"
