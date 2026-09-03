"""UNDERSTAND: turn one question into structured, validated user intent.

This package owns *what the user means*. It never decides what FireLens is
allowed to establish; that is the planner's job (BOUND).
"""

from firelens.understanding.place import PlaceKind, PlaceMention, extract_place

__all__ = ["PlaceKind", "PlaceMention", "extract_place"]
