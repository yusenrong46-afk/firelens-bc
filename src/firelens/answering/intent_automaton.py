"""Typed request parser for operations; it never grants publication authority."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache

from firelens.answering import intent_lexicon as lex
from firelens.answering import intent_spans as spans
from firelens.answering.intent_automaton_rules import is_selected_prediction
from firelens.answering.intent_guidance import is_evac_definition, is_guidance
from firelens.answering.intent_refresh import is_refresh_snapshot_tokens
from firelens.contracts import LiveResultKind


class ClauseIntentKind(StrEnum):
    """Application-owned clause classes; none grants publication authority."""

    LIVE_RECORDS = "live_records"
    REVIEWED_GUIDANCE = "reviewed_guidance"
    PRODUCT_HELP = "product_help"
    STATIC_BACKGROUND = "static_background"
    OTHER = "other"


class TemporalScope(StrEnum):
    """Time ownership used to prevent historical/future text becoming live."""

    CURRENT = "current"
    NONCURRENT = "noncurrent"
    UNSPECIFIED = "unspecified"


class RecordOperation(StrEnum):
    """Bounded operations supported by deterministic live-record tools."""

    LIST = "list"
    LOCATE = "locate"
    STATUS = "status"
    ANALYZE = "analyze"
    PERIMETER = "perimeter"
    EVACUATION = "evacuation"


def _temporal_scope(tokens: tuple[str, ...], text: str) -> TemporalScope:
    token_set = frozenset(tokens)
    current = bool(
        token_set & lex.CURRENT_WORDS or lex.has_any_phrase(tokens, lex.CURRENT_PHRASES)
    )
    noncurrent = bool(
        token_set & lex.NONCURRENT_WORDS
        or lex.has_any_phrase(tokens, lex.NONCURRENT_PHRASES)
        or lex.YEAR.search(text)
    )
    if is_selected_prediction(tokens):
        return TemporalScope.CURRENT
    if noncurrent:
        return TemporalScope.NONCURRENT
    if current:
        return TemporalScope.CURRENT
    return TemporalScope.UNSPECIFIED


def _is_universal_distance(tokens: tuple[str, ...]) -> bool:
    token_set = frozenset(tokens)
    return bool(
        token_set & {"distance", "radius", "far"}
        and (
            token_set & {"everyone", "everybody", "universal"}
            or lex.has_phrase(tokens, ("every", "resident"))
            or lex.has_phrase(tokens, ("every", "family"))
            or lex.has_phrase(tokens, ("every", "wildfire"))
            or lex.has_phrase(tokens, ("every", "person"))
            or lex.has_phrase(tokens, ("one", "exact"))
        )
    )


def _looks_like_clause(text: str) -> bool:
    tokens = lex.tokenize(text)
    if not tokens:
        return False
    guidance_heads = {
        "a",
        "advice",
        "an",
        "basic",
        "emergency",
        "evacuation",
        "grab",
        "guidance",
        "packing",
        "plain",
        "official",
        "simple",
        "smoke",
        "the",
        "tips",
        "what",
        "wildfire",
        "structure",
    }
    return bool(
        tokens[0] in lex.REQUEST_STARTERS
        or (tokens[0] in guidance_heads and is_guidance(tokens[:12]))
        or (
            tokens[0] in guidance_heads
            and frozenset(tokens[:16])
            & {"advice", "checklist", "guidance", "preparedness", "readiness", "tips"}
        )
    )


def _split_clauses(question: str) -> tuple[str, ...]:
    """Split only at a new request head or an explicit `+`, `?`, or `;`."""

    question = lex.normalize_text(question).strip()
    if not question:
        return (question,)
    pieces: list[str] = []
    start = 0
    for match in lex.TOP_LEVEL_SEPARATOR.finditer(question):
        left = question[start : match.start()].strip(" ,.?;+")
        right = question[match.end() :].strip(" ,.?;+")
        separator = match.group(0)
        explicit = bool(re.search(r"[+?;]", separator))
        if left and right and (explicit or _looks_like_clause(right)):
            pieces.append(left)
            start = match.end()
    tail = question[start:].strip(" ,.?;+")
    if tail:
        pieces.append(tail)
    result = tuple(
        re.sub(r"^(?:and|also|but|then)\s+", "", piece, flags=re.IGNORECASE)
        for piece in (tuple(pieces) or (question,))
    )
    fronted = lex.FRONTED_SCOPE.search(question)
    if (
        fronted is not None
        and len(result) >= 2
        and result[0].casefold().strip() == fronted.group("place").casefold().strip()
        and spans.plausible_fronted_scope(fronted.group("place"))
    ):
        separator = fronted.group("separator")
        if separator.casefold().strip() == "plus":
            separator = " plus "
        else:
            separator = f"{separator} "
        result = (f"{result[0]}{separator}{result[1]}", *result[2:])
    return result


def _is_product_help(tokens: tuple[str, ...]) -> bool:
    token_set = frozenset(tokens)
    if token_set & lex.UI_OBJECTS and token_set & lex.UI_ACTIONS:
        return True
    return bool(
        "firelens" in token_set
        and token_set & {"how", "what"}
        and token_set & {"map", "maps", "work", "works", "data", "citations"}
        and not (token_set & lex.SCOPE_WORDS)
    )


def _is_expository(tokens: tuple[str, ...]) -> bool:
    token_set = frozenset(tokens)
    return bool(
        token_set & lex.EXPOSITORY_WORDS or lex.has_phrase(tokens, ("tell", "me", "about"))
    )


def _is_geography_analysis(tokens: tuple[str, ...]) -> bool:
    token_set = frozenset(tokens)
    return bool(
        token_set
        & {
            "concentrated",
            "concentration",
            "density",
            "distributed",
            "distribution",
            "geographic",
            "geographically",
            "geography",
            "regions",
        }
        or lex.has_phrase(tokens, ("fire", "centre"))
        or lex.has_phrase(tokens, ("fire", "centres"))
        or lex.has_phrase(tokens, ("by", "region"))
        or lex.has_phrase(tokens, ("by", "area"))
        or lex.has_phrase(tokens, ("how", "many"))
        or ("compare" in token_set and token_set & {"and", "versus", "vs"})
        or (
            token_set & {"north", "northern", "south", "southern"}
            and token_set & {"bc", "columbia"}
        )
    )


def _is_record_analysis(tokens: tuple[str, ...]) -> bool:
    token_set = frozenset(tokens)
    return bool(
        token_set & {"count", "counts", "fewest", "largest", "most", "oldest"}
        or _is_geography_analysis(tokens)
    )


def _guidance_blocks_live(tokens: tuple[str, ...], temporal: TemporalScope) -> bool:
    """Reviewed guidance may share a clause with a live ask; only block live then."""

    if not is_guidance(tokens):
        return False
    token_set = frozenset(tokens)
    if token_set & lex.DEFINITION_WORDS:
        return True
    asked_live_records = bool(token_set & lex.LIVE_RECORD_ASK_COMMANDS)
    if token_set & {"advice", "guidance", "tips", "checklist"} and not asked_live_records:
        return True
    if token_set & {"preparedness", "readiness"} and not asked_live_records:
        live_status_ask = bool(
            token_set & (lex.EVACUATION_WORDS | lex.FIRE_WORDS | lex.PERIMETER_WORDS)
            and token_set & {"active", "burning", "happening", "listed", "reported"}
        )
        if not live_status_ask:
            return True
    return not bool(
        temporal == TemporalScope.CURRENT
        or token_set & lex.LIVE_RECORD_ASK_COMMANDS
        or lex.has_phrase(tokens, ("is", "there"))
        or lex.has_phrase(tokens, ("are", "there"))
    )


def _current_fire_operation(
    tokens: tuple[str, ...], temporal: TemporalScope
) -> RecordOperation | None:
    token_set = frozenset(tokens)
    if _is_universal_distance(tokens):
        return None
    if "safe" in token_set and token_set & {"distance", "separation"}:
        return None
    fire = lex.has_fire(tokens)
    perimeter = bool(token_set & lex.PERIMETER_WORDS)
    map_focus = bool(
        "map" in token_set
        and (
            (
                token_set & {"center", "centre", "focus", "move", "put"}
                and token_set & {"at", "around", "near", "on", "where"}
            )
            or (tokens[0] == "map" and 2 <= len(tokens) <= 5)
        )
    )
    official_records = bool(
        "official" in token_set
        and token_set & {"record", "records"}
        and (token_set & lex.SCOPE_WORDS or token_set & {"what", "which", "show"})
    )
    if map_focus or official_records:
        return RecordOperation.LOCATE if map_focus else RecordOperation.LIST
    if not fire and not perimeter:
        return None
    if fire and is_refresh_snapshot_tokens(tokens):
        return RecordOperation.LIST
    if is_selected_prediction(tokens):
        return RecordOperation.STATUS
    if temporal == TemporalScope.NONCURRENT:
        return None
    if _is_product_help(tokens) or _guidance_blocks_live(tokens, temporal):
        return None
    if (
        fire
        and token_set & {"near", "nearby", "closest", "nearest"}
        and re.search(r"\b(?:near|nearby|to|from)\s+(?:me|us|my|our)\b", " ".join(tokens))
    ):
        return RecordOperation.LOCATE
    current = temporal == TemporalScope.CURRENT
    command = bool(token_set & lex.RECORD_COMMANDS)
    record_noun = bool(token_set & lex.RECORD_NOUNS)
    scoped = bool(token_set & lex.SCOPE_WORDS)
    active_state = bool(token_set & {"active", "burning", "happening", "listed", "reported"})
    wh = bool(token_set & {"what", "where", "which"})
    existential = lex.has_phrase(tokens, ("is", "there")) or lex.has_phrase(
        tokens, ("are", "there")
    )
    explicit_record = bool(token_set & {"incident", "incidents", "perimeter", "perimeters"})
    plural_fire = bool(
        token_set & {"fires", "wildfires", "incidents"}
        or any(token.endswith("fires") for token in tokens)
    )
    named_fire_location = bool(
        "where" in token_set
        and ("fire" in token_set or "wildfire" in token_set)
        and (scoped or tokens[-1] in {"fire", "wildfire"} or len(tokens) >= 4)
    )
    context_only = bool(
        token_set & lex.CONTEXT_ONLY_WORDS
        and not explicit_record
        and not (command and fire and (scoped or plural_fire))
    )
    if context_only or _is_expository(tokens):
        return None
    if bool(token_set & {"distance", "far", "close", "closest", "nearest"}) and (
        fire or perimeter
    ):
        perimeter_only = perimeter and not token_set & {
            "fires",
            "wildfires",
            "incident",
            "incidents",
        }
        return (
            RecordOperation.PERIMETER
            if perimeter_only or (perimeter and not fire)
            else RecordOperation.LOCATE
        )
    if _is_geography_analysis(tokens) or _is_record_analysis(tokens):
        return RecordOperation.ANALYZE
    if perimeter and (command or current or wh or existential):
        return RecordOperation.PERIMETER
    if named_fire_location:
        return RecordOperation.LOCATE
    if existential and fire and (scoped or current or active_state):
        return RecordOperation.LIST
    if existential and fire and token_set & {"called", "named"}:
        return RecordOperation.LIST
    if wh and plural_fire and (scoped or current or active_state or record_noun):
        return RecordOperation.LIST
    if fire and (
        current
        or active_state
        or (command and (plural_fire or explicit_record or record_noun or scoped))
        or record_noun
        or "any" in token_set
        or (plural_fire and scoped)
        or (
            2 <= len(tokens) <= 5
            and lex.is_fire_token(tokens[-1])
            and tokens[0] not in {"a", "an", "the", "what", "why"}
        )
    ):
        return RecordOperation.STATUS
    return None


def _current_evacuation(tokens: tuple[str, ...], temporal: TemporalScope) -> bool:
    token_set = frozenset(tokens)
    if _is_universal_distance(tokens) or is_evac_definition(tokens):
        return False
    emergency_service = bool(
        "emergencyinfobc" in token_set or ("emergencyinfo" in token_set and "bc" in token_set)
    )
    evacuation = bool(
        token_set & lex.EVACUATION_WORDS
        or token_set & {"evacuating", "evacuated"}
        or emergency_service
    )
    if not evacuation or temporal == TemporalScope.NONCURRENT:
        return False
    if _is_expository(tokens) or _guidance_blocks_live(tokens, temporal):
        return False
    return bool(
        temporal == TemporalScope.CURRENT
        or token_set & lex.RECORD_COMMANDS
        or token_set & lex.SCOPE_WORDS
        or token_set & {"active", "issued", "new", "post", "posted"}
        or (
            token_set & {"alert", "alerts", "order", "orders"}
            and token_set & {"do", "does", "have", "is", "on", "under", "where", "whether"}
        )
        or emergency_service
        or lex.has_phrase(tokens, ("is", "there"))
        or lex.has_phrase(tokens, ("are", "there"))
    )


def _generic_official_records(tokens: tuple[str, ...]) -> bool:
    token_set = frozenset(tokens)
    return bool(
        "official" in token_set
        and token_set & {"record", "records"}
        and not token_set
        & {
            "fire",
            "fires",
            "wildfire",
            "wildfires",
            "incident",
            "incidents",
            "perimeter",
            "perimeters",
        }
    )


@dataclass(frozen=True, slots=True)
class ParsedClauseIntent:
    """One atomic request clause classified before policy and retrieval."""

    text: str
    tokens: tuple[str, ...]
    kind: ClauseIntentKind
    temporal_scope: TemporalScope
    operation: RecordOperation | None
    live_layers: tuple[LiveResultKind, ...]
    live_location_candidate: str | None

    @property
    def is_live(self) -> bool:
        return bool(self.live_layers)

    @property
    def is_noncurrent_fire(self) -> bool:
        token_set = frozenset(self.tokens)
        return bool(
            self.temporal_scope == TemporalScope.NONCURRENT
            and (lex.has_fire(self.tokens) or token_set & lex.PERIMETER_WORDS)
            and not token_set & lex.CONTEXT_ONLY_WORDS
        )

    @property
    def contributes_static_subrequest(self) -> bool:
        if self.is_live or self.kind == ClauseIntentKind.PRODUCT_HELP:
            return False
        if spans.is_context_location_declaration(self.text):
            return False
        if self.kind in {
            ClauseIntentKind.REVIEWED_GUIDANCE,
            ClauseIntentKind.STATIC_BACKGROUND,
        }:
            return True
        return "happening" not in frozenset(self.tokens)


@dataclass(frozen=True, slots=True)
class ParsedRequestIntent:
    """Single source of truth for deterministic request-shape consumers."""

    original_question: str
    clauses: tuple[ParsedClauseIntent, ...]
    requests_non_bc_scope: bool

    @property
    def has_live_records(self) -> bool:
        return any(clause.is_live for clause in self.clauses)

    @property
    def has_reviewed_guidance(self) -> bool:
        return any(clause.kind == ClauseIntentKind.REVIEWED_GUIDANCE for clause in self.clauses)

    @property
    def has_prefetchable_guidance(self) -> bool:
        if self.has_reviewed_guidance:
            return True
        tokens = frozenset(token for clause in self.clauses for token in clause.tokens)
        return bool(tokens & lex.PREFETCH_GUIDANCE_TOKENS) or bool(
            self.has_live_records
            and any(
                {"what", "should", "have", "ready"}.issubset(frozenset(clause.tokens))
                for clause in self.clauses
                if not clause.is_live
            )
        )

    @property
    def live_layers(self) -> tuple[LiveResultKind, ...]:
        return tuple(
            dict.fromkeys(layer for clause in self.clauses for layer in clause.live_layers)
        )

    @property
    def temporal_scope(self) -> TemporalScope:
        scopes = {clause.temporal_scope for clause in self.clauses}
        if TemporalScope.CURRENT in scopes:
            return TemporalScope.CURRENT
        if TemporalScope.NONCURRENT in scopes:
            return TemporalScope.NONCURRENT
        return TemporalScope.UNSPECIFIED

    @property
    def live_location_candidates(self) -> tuple[str, ...]:
        return tuple(
            candidate
            for clause in self.clauses
            if (candidate := clause.live_location_candidate) is not None
        )

    @property
    def reviewed_guidance_text(self) -> str | None:
        selected = [
            clause.text
            for clause in self.clauses
            if clause.kind == ClauseIntentKind.REVIEWED_GUIDANCE
        ]
        return " and ".join(selected)[:2_000] if selected else None

    @property
    def static_subrequest_text(self) -> str | None:
        selected = [
            clause.text for clause in self.clauses if clause.contributes_static_subrequest
        ]
        return " and ".join(selected)[:2_000] if selected else None


def _parse_clause(text: str) -> ParsedClauseIntent:
    tokens = lex.tokenize(text)
    token_set = frozenset(tokens)
    temporal = _temporal_scope(tokens, text)
    product_help = _is_product_help(tokens)
    guidance = is_guidance(tokens)
    fire_operation = (
        RecordOperation.LIST
        if lex.COMPACT_RADIUS_SCOPE.search(text)
        else (
            RecordOperation.LOCATE
            if lex.LIVE_RECORDS_CLOSEST_SCOPE.search(text)
            else _current_fire_operation(tokens, temporal)
        )
    )
    evacuation = _current_evacuation(tokens, temporal)
    layers: list[LiveResultKind] = []
    operation = fire_operation
    if fire_operation == RecordOperation.ANALYZE:
        if token_set & {"hectare", "hectares", "largest", "oldest"}:
            layers.extend((LiveResultKind.INCIDENT, LiveResultKind.PERIMETER))
        else:
            layers.append(LiveResultKind.INCIDENT)
    elif fire_operation == RecordOperation.PERIMETER:
        if token_set & {"fires", "wildfires", "incident", "incidents"}:
            layers.extend((LiveResultKind.INCIDENT, LiveResultKind.PERIMETER))
        else:
            layers.append(LiveResultKind.PERIMETER)
    elif fire_operation is not None:
        layers.extend((LiveResultKind.INCIDENT, LiveResultKind.PERIMETER))
        if _generic_official_records(tokens):
            layers.append(LiveResultKind.EVACUATION)
    if evacuation:
        layers.append(LiveResultKind.EVACUATION)
        operation = operation or RecordOperation.EVACUATION
    if layers:
        kind = ClauseIntentKind.LIVE_RECORDS
    elif guidance:
        kind = ClauseIntentKind.REVIEWED_GUIDANCE
    elif product_help:
        kind = ClauseIntentKind.PRODUCT_HELP
    elif lex.has_fire(tokens) or token_set & (lex.PERIMETER_WORDS | lex.EVACUATION_WORDS):
        kind = ClauseIntentKind.STATIC_BACKGROUND
    else:
        kind = ClauseIntentKind.OTHER
    live_layers = tuple(dict.fromkeys(layers))
    candidate = None
    if live_layers and fire_operation != RecordOperation.ANALYZE:
        candidate = spans.location_candidate(text, is_live=True)
    return ParsedClauseIntent(
        text=text,
        tokens=tokens,
        kind=kind,
        temporal_scope=temporal,
        operation=operation,
        live_layers=live_layers,
        live_location_candidate=candidate,
    )


@lru_cache(maxsize=2_048)
def parse_request_intent(question: str) -> ParsedRequestIntent:
    """Parse one question once into immutable typed request intent."""

    normalized = lex.normalize_text(question)
    split_texts = _split_clauses(normalized)
    implicit_location = spans.implicit_nearby_location(normalized)
    if implicit_location is not None and len(split_texts) == 1:
        clause = ParsedClauseIntent(
            text=normalized.strip(" ,.?;+"),
            tokens=lex.tokenize(normalized),
            kind=ClauseIntentKind.LIVE_RECORDS,
            temporal_scope=TemporalScope.UNSPECIFIED,
            operation=RecordOperation.LIST,
            live_layers=(
                LiveResultKind.INCIDENT,
                LiveResultKind.PERIMETER,
                LiveResultKind.EVACUATION,
            ),
            live_location_candidate=implicit_location,
        )
        return ParsedRequestIntent(
            original_question=question,
            clauses=(clause,),
            requests_non_bc_scope=spans.requests_non_bc_scope(clause.tokens),
        )
    texts = split_texts
    clauses = [_parse_clause(text) for text in texts]
    if implicit_location is not None:
        for index, clause in enumerate(clauses):
            nearby_clause = bool(
                lex.NEARBY_INFORMATION_REQUEST.search(clause.text)
                or lex.NEAR_PLACE_INFORMATION_REQUEST.search(clause.text)
            )
            if not nearby_clause or clause.is_live:
                continue
            clauses[index] = ParsedClauseIntent(
                text=clause.text,
                tokens=clause.tokens,
                kind=ClauseIntentKind.LIVE_RECORDS,
                temporal_scope=clause.temporal_scope,
                operation=RecordOperation.LIST,
                live_layers=(
                    LiveResultKind.INCIDENT,
                    LiveResultKind.PERIMETER,
                    LiveResultKind.EVACUATION,
                ),
                live_location_candidate=implicit_location,
            )
            break
    fronted_scope = spans.fronted_scope_for_question(normalized)
    if fronted_scope is not None:
        for index, clause in enumerate(clauses):
            if clause.is_live and clause.live_location_candidate is None:
                clauses[index] = ParsedClauseIntent(
                    text=clause.text,
                    tokens=clause.tokens,
                    kind=clause.kind,
                    temporal_scope=clause.temporal_scope,
                    operation=clause.operation,
                    live_layers=clause.live_layers,
                    live_location_candidate=fronted_scope,
                )
                break
    parsed = ParsedRequestIntent(
        original_question=question,
        clauses=tuple(clauses),
        requests_non_bc_scope=False,
    )
    return ParsedRequestIntent(
        original_question=question,
        clauses=parsed.clauses,
        requests_non_bc_scope=(
            parsed.has_live_records and spans.requests_non_bc_scope(lex.tokenize(normalized))
        ),
    )


def clear_intent_cache() -> None:
    """Clear the bounded parser cache after an intentional code/data reload."""

    parse_request_intent.cache_clear()
