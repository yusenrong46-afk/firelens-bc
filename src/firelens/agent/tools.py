"""The fixed V3 tool vocabulary; no model-defined or arbitrary tools are allowed."""

from enum import StrEnum


class AgentTool(StrEnum):
    LIST_ACTIVE_FIRES = "list_active_fires"
    GET_FIRE_DETAILS = "get_fire_details"
    GET_EVACUATION_INFORMATION = "get_evacuation_information"
    CALCULATE_FIRE_DISTANCE = "calculate_fire_distance"
    SEARCH_REVIEWED_GUIDANCE = "search_reviewed_guidance"
    ANSWER_GENERAL_BACKGROUND = "answer_general_background"
