"""Deterministic high-risk and capability routing.

Only decisions that must never depend on a model live here.  Ordinary questions
continue to the bounded conversational planner instead of being rejected by a
small domain-keyword list.
"""

from __future__ import annotations

import re

from firelens.answering.capability_intent import is_capability_question
from firelens.answering.intent_patterns import (
    _CORPUS_REFERENCE_PATTERNS,
    _LIVE_PATTERNS,
    _PERSONALIZED_MEDICAL_PATTERNS,
    _POLICY_MANIPULATION_PATTERNS,
    _PROHIBITED_PATTERNS,
)
from firelens.answering.intent_safety import (
    empty_map_safety_routing,
    is_empty_map_safety_inference,
    trust_explanation_limitations,
)
from firelens.answering.live_record_intent import (
    is_fire_geography_analysis,
    is_fire_record_analysis,
)
from firelens.answering.location_intent import (
    asks_for_personal_location,
    coarse_location_from_question,
)
from firelens.answering.request_grammar import parse_request_facets
from firelens.answering.return_intent import reviewed_return_condition_intent
from firelens.contracts import (
    AuthorityClass,
    LiveResultKind,
    PlanningDecision,
    QueryPlan,
    QueryRelation,
    QueryRequest,
    QueryRoute,
    ReasonCode,
    RetrievalRequest,
)

STATIC_LIMITATION = "This answer uses stable guidance and does not provide current status."

TOPIC_CATALOGUE: tuple[tuple[str, str], ...] = (
    (
        "Household emergency planning",
        "How should I build and review a household emergency plan?",
    ),
    ("Emergency kits and grab-and-go bags", "What belongs in an emergency kit?"),
    (
        "Evacuation alerts and orders",
        "What is the difference between an evacuation alert and order?",
    ),
    ("Wildfire smoke", "How can I prepare for wildfire smoke?"),
    ("FireSmart home preparation", "How can I reduce combustible material around my home?"),
    ("Wildfire rank and stages of control", "What do wildfire rank and stage of control mean?"),
    (
        "Structure-protection sprinklers",
        "What should I know about structure-protection sprinklers?",
    ),
)

SUGGESTED_QUESTIONS: tuple[str, ...] = tuple(item[1] for item in TOPIC_CATALOGUE)

_CURRENT_CUE_TEXT = (
    r"(?:right now|currently|current|latest|today|tonight|tomorrow|now|at the moment)"
)
_CURRENT_CUE = re.compile(rf"\b{_CURRENT_CUE_TEXT}\b", re.IGNORECASE)
_EXPLANATORY_UNSUPPORTED = re.compile(
    r"\b(?:what\s+(?:does|do)\b.{0,80}\bmean|what\s+is\s+an?\b|"
    r"(?:explain|define)\b|how\s+does\b.{0,80}\b(?:affect|work))",
    re.IGNORECASE,
)
_UNSUPPORTED_LIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "air quality",
        re.compile(
            rf"\b(?:what|how)\s+(?:is|are)\s+(?:the\s+)?"
            rf"(?:air quality|aqhi|smoke conditions?)\b|"
            rf"\bis\s+(?:it|.{{1,50}})\s+smoky\b|"
            rf"\b{_CURRENT_CUE_TEXT}\b.{{0,60}}\b"
            rf"(?:air quality|aqhi|smoke conditions?|smoky)\b|"
            rf"\b(?:air quality|aqhi|smoke conditions?|smoky)\b.{{0,60}}"
            rf"\b{_CURRENT_CUE_TEXT}\b",
            re.IGNORECASE,
        ),
    ),
    (
        "road conditions",
        re.compile(
            r"\b(?:roads?|highways?|routes?)\b.{0,40}"
            r"\b(?:open|closed|closures?|blocked|conditions?)\b|"
            r"\b(?:open|closed|closures?|blocked|conditions?)\b.{0,40}"
            r"\b(?:roads?|highways?|routes?)\b|"
            r"\bsafe\s+to\s+(?:drive|travel)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "weather or smoke forecast",
        re.compile(
            rf"\bwhat\s+will\s+(?:the\s+)?(?:wind|weather|smoke)\b|"
            rf"\b(?:wind|weather|smoke)\b.{{0,60}}"
            rf"\b(?:forecast|speed|direction|{_CURRENT_CUE_TEXT})\b|"
            rf"\b(?:forecast|{_CURRENT_CUE_TEXT})\b.{{0,60}}"
            rf"\b(?:wind|weather|smoke)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "firefighting aircraft",
        re.compile(
            r"\b(?:where|show|display|track|locate)\b.{0,60}"
            r"\b(?:firefighting\s+)?(?:aircraft|airtankers?|air tankers?|helicopters?)\b|"
            rf"\b(?:aircraft|airtankers?|air tankers?|helicopters?)\b.{{0,60}}"
            rf"\b{_CURRENT_CUE_TEXT}\b|"
            rf"\b{_CURRENT_CUE_TEXT}\b.{{0,60}}"
            r"\b(?:firefighting\s+)?(?:aircraft|airtankers?|air tankers?|helicopters?)\b",
            re.IGNORECASE,
        ),
    ),
)
_EVACUATION_TOPIC = re.compile(
    r"\b(?:evacuations?|(?:(?:evacuation|evac)\s+)?(?:alerts?|orders?)|"
    r"emergencyinfo\s*bc)\b",
    re.IGNORECASE,
)
_EVACUATION_DEFINITION = re.compile(
    r"\b(?:explain|define|meaning|mean|difference|versus|vs\.?)\b.{0,80}"
    r"\b(?:alerts?|orders?)\b|"
    r"\b(?:alerts?|orders?)\b.{0,80}"
    r"\b(?:mean|meaning|difference|versus|vs\.?)\b",
    re.IGNORECASE,
)
_STATIC_GUIDANCE_TERMS = (
    "prepare",
    "preparedness",
    "precaution",
    "kit",
    "bag",
    "grab-and-go",
    "firesmart",
    "reduce wildfire risk",
    "sprinkler",
    "smoke exposure",
    "protect from smoke",
    "alert mean",
    "order mean",
)


def request_fragments(question: str) -> tuple[str, ...]:
    """Split top-level request clauses without breaking alert/order definitions."""

    return parse_request_facets(question).clause_texts


_REVIEWED_GUIDANCE_PATTERNS = (
    r"\b(?:home ignition zone|firesmart|combustible material|ember risk)\b",
    r"\bprecautions?\b",
    r"\bwhat should i (?:take|do|pack|prepare)\b.{0,80}\b(?:fire|wildfire|evacuat)",
    r"\b(?:grab-and-go|go bag|emergency kit|emergency plan(?:ning)?|household plan)\b",
    r"\b(?:family|household|pets?)\b.{0,50}\b(?:prepare|evacuation|emergency)\b",
    r"\b(?:prepare|preparing)\b.{0,50}\b(?:family|household|pets?|evacuation)\b",
    r"\b(?:evacuation|evac)[-\s]+(?:alerts?|orders?)\b"
    r"(?:.{0,40}\b(?:basics?|summar(?:y|ies)|overview|guidance)\b)?",
    r"\b(?:wildfire smoke|smoke indoors?|smoke exposure|smoke\s+(?:in|inside)\s+(?:my\s+|our\s+|the\s+)?(?:home|house))\b",
    r"\b(?:wildfire rank|stage of control|stages of control)\b",
    r"\b(?:out(?:ta| of) control|being held|under control)\b.{0,30}\b(?:fire|wildfire|mean)\b",
    r"\b(?:structure[- ]protection sprinklers?|home ignition)\b",
)

_DEICTIC_FOLLOWUP = re.compile(
    r"\b(?:it|that|this|they|them|there|those|these|the (?:first|second|third|other) one|"
    r"that (?:guidance|system|advice|status)|right now|what about now)\b"
)


def focused_question(question: str) -> str:
    """Remove a long obvious preamble while preserving the final explicit question.

    This is deliberately structural rather than topic-aware: it cannot introduce
    vocabulary or choose an answer, and it leaves ordinary multi-sentence requests
    untouched.
    """

    if len(question) < 500:
        return question
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", question)]
    explicit = [part for part in sentences if part.endswith("?") and len(part.split()) >= 4]
    if explicit and len(explicit[-1]) <= 500:
        return explicit[-1]
    return question


def resolved_user_question(request: QueryRequest) -> str:
    """Name the previous user subject for a genuinely elliptical follow-up."""

    current = focused_question(request.question)
    if len(current.split()) > 16 or not _DEICTIC_FOLLOWUP.search(current.casefold()):
        return current
    previous = [turn.content for turn in request.history if turn.role == "user"]
    if not previous:
        return current
    return f"Regarding the earlier question '{previous[-1]}', {current}"[:2_000]


def _routing_texts(request: QueryRequest) -> tuple[str, ...]:
    """Use history only for a genuinely elliptical current question."""

    current = focused_question(request.question).lower()
    if len(current.split()) > 16 or not _DEICTIC_FOLLOWUP.search(current):
        return (current,)
    previous = [turn.content for turn in request.history if turn.role == "user"]
    return (current, f"{previous[-1].lower()} {current}") if previous else (current,)


def _deictic_action_boundary(request: QueryRequest) -> ReasonCode | None:
    """Resolve only a narrow "should I do that" high-risk antecedent."""

    lowered = request.question.lower()
    if not re.search(
        r"\bshould\s+(?:i|we)\s+(?:do|follow|take|use)\s+(?:that|this|it)\b|"
        r"\bshould\s+(?:i|we)\s+take\s+(?:that|this|the)\s+(?:road|route|way)\b|"
        r"\b(?:can|could|may)\s+(?:i|we)\s+return\b|"
        r"\bis it safe to do that\b",
        lowered,
    ):
        return None
    antecedent = " ".join(turn.content.lower() for turn in request.history[-2:])
    if any(
        term in antecedent for term in ("dose", "inhaler", "medication", "prescribe", "diagnos")
    ):
        return ReasonCode.PERSONALIZED_MEDICAL_ADVICE
    if any(
        term in antecedent
        for term in (
            "leave",
            "evacuat",
            "return",
            "stay",
            "route",
            "road",
            "alert",
            "order",
        )
    ):
        return ReasonCode.PERSONALIZED_SAFETY_DECISION
    return None


def required_authorities(question: str) -> frozenset[AuthorityClass]:
    """Infer broad authority needs without forcing a mixed question into one class."""

    lowered = question.lower()
    required: set[AuthorityClass] = set()

    def contains(terms: tuple[str, ...]) -> bool:
        return any(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", lowered) for term in terms)

    if contains(("smoke", "air quality", "health", "asthma")):
        required.add(AuthorityClass.PROVINCIAL_PUBLIC_HEALTH)
    if contains(
        (
            "evacuation alert",
            "evacuation order",
            "grab-and-go",
            "go bag",
            "emergency kit",
            "emergency plan",
            "wildfire rank",
            "stage of control",
        )
    ):
        required.add(AuthorityClass.PROVINCIAL_GOVERNMENT)
    if contains(("firesmart", "sprinkler", "home ignition", "combustible", "ember")):
        required.add(AuthorityClass.WILDFIRE_PREPAREDNESS)
    return frozenset(required)


def _requires_personal_live_location(question: str) -> bool:
    lowered = question.casefold()
    if not asks_for_personal_location(question):
        return False
    if re.search(
        r"\b(?:reduce|lower|prepare|protect|firesmart)\b.{0,50}\b(?:risk|home|house|property)\b|"
        r"\b(?:wildfire|fire)\s+risk\b",
        lowered,
    ):
        return False
    return bool(
        re.search(
            r"\b(?:fires?|wildfires?|burning|map|perimeter|evacuation|alert|order|"
            r"closest|nearest)\b",
            lowered,
        )
    )


def live_layers_for_question(question: str) -> tuple[LiveResultKind, ...]:
    """Return only official layers that can answer the user's live intent."""

    original_question = question
    facets = parse_request_facets(original_question)
    if facets.only_non_current_fire:
        return ()
    original_location = coarse_location_from_question(original_question)
    if (
        original_location is None
        and re.search(
            r"\b(?:this|that|selected)\s+(?:fire|wildfire|incident|record)\b",
            original_question,
            re.IGNORECASE,
        )
        and re.search(
            r"\b(?:status|details?|size|large|big|hectares?|source|updated|updates?)\b",
            original_question,
            re.IGNORECASE,
        )
    ):
        # Deictic attributes must bind to a selected ID, never a province list.
        return ()
    supported_fragments = [
        clause.text
        for clause in facets.clauses
        if clause.current_live_fire or not unsupported_live_topics(clause.text)
    ]
    if not supported_fragments:
        return ()
    question = " and ".join(supported_fragments)
    lowered = question.casefold()
    layers: list[LiveResultKind] = []
    # RequestFacets is the sole incident-current authority.
    fire_status_requested = facets.has_current_live_fire
    perimeter_requested = bool(re.search(r"\bperimeters?\b", lowered))
    incident_requested = bool(re.search(r"\bincidents?\b", lowered))
    perimeter_only_phrase = bool(re.search(r"\b(?:fire|wildfire)\s+perimeters?\b", lowered))
    if facets.has_current_live_fire and is_fire_geography_analysis(question):
        # Fire-centre geography is an incident-layer field. Pulling perimeter
        # polygons here duplicates fires, inflates status totals, and sends the
        # browser records that cannot contribute to this analysis.
        layers.append(LiveResultKind.INCIDENT)
    elif perimeter_requested and not incident_requested and perimeter_only_phrase:
        layers.append(LiveResultKind.PERIMETER)
    elif perimeter_requested and not fire_status_requested:
        if incident_requested:
            layers.extend((LiveResultKind.INCIDENT, LiveResultKind.PERIMETER))
        else:
            layers.append(LiveResultKind.PERIMETER)
    elif fire_status_requested:
        layers.extend((LiveResultKind.INCIDENT, LiveResultKind.PERIMETER))
        if original_location is not None and re.search(
            r"\bofficial\s+(?:live\s+)?records?\b", lowered
        ):
            # A location-scoped request for generic official records asks for
            # every map layer FireLens owns, not only incident records.
            layers.append(LiveResultKind.EVACUATION)
    elif (
        facets.has_current_live_fire
        and re.search(r"\bincident\b", lowered)
        and re.search(r"\bperimeter\b", lowered)
    ):
        layers.extend((LiveResultKind.INCIDENT, LiveResultKind.PERIMETER))
    if any(
        _EVACUATION_TOPIC.search(fragment)
        and plan_query(QueryRequest(question=fragment)).route == QueryRoute.LIVE
        for fragment in request_fragments(original_question)
    ):
        layers.append(LiveResultKind.EVACUATION)
    if is_empty_map_safety_inference(original_question):
        # An empty fire map cannot establish evacuation status or personal safety.
        # Fetch every owned official layer so the response can expose the whole
        # bounded lookup and hand off to the issuing authority without an all-clear.
        layers.extend(
            (
                LiveResultKind.INCIDENT,
                LiveResultKind.PERIMETER,
                LiveResultKind.EVACUATION,
            )
        )
    if (
        not layers
        and facets.has_current_live_fire
        and (is_fire_geography_analysis(question) or is_fire_record_analysis(question))
        and re.search(
            r"\b(?:fires?|wildfires?|[a-z]{1,12}fires?)\b",
            lowered,
        )
    ):
        layers.extend((LiveResultKind.INCIDENT, LiveResultKind.PERIMETER))
    return tuple(dict.fromkeys(layers))


def unsupported_live_topics(question: str) -> tuple[str, ...]:
    fragments = request_fragments(question)
    return tuple(
        label
        for label, pattern in _UNSUPPORTED_LIVE_PATTERNS
        if any(
            pattern.search(fragment)
            and not (
                _EXPLANATORY_UNSUPPORTED.search(fragment) and not _CURRENT_CUE.search(fragment)
            )
            for fragment in fragments
        )
    )


def live_query_requires_location(question: str) -> bool:
    """Require opt-in only when the user refers to an unstated personal location."""

    return _requires_personal_live_location(question)


def static_guidance_fragment(question: str) -> str | None:
    """Keep the user's own stable-guidance clause for a mixed live/static request."""

    fragments = parse_request_facets(question).clause_texts
    selected = [
        fragment
        for fragment in fragments
        if fragment
        and (
            any(term in fragment.casefold() for term in _STATIC_GUIDANCE_TERMS)
            or any(
                re.search(pattern, fragment.casefold())
                for pattern in _REVIEWED_GUIDANCE_PATTERNS
            )
            or reviewed_return_condition_intent(fragment)
            or _EVACUATION_DEFINITION.search(fragment)
        )
        and plan_query(QueryRequest(question=fragment)).route == QueryRoute.RELATED
    ]
    if not selected:
        return None
    return " and ".join(selected)[:2_000]


def reviewed_guidance_intent(question: str) -> bool:
    """Recognize only topics represented by the reviewed static collection."""

    lowered = question.casefold()
    return reviewed_return_condition_intent(question) or any(
        re.search(pattern, lowered) for pattern in _REVIEWED_GUIDANCE_PATTERNS
    )


def plan_query(request: QueryRequest, *, allow_live: bool = True) -> QueryPlan:
    """Apply the zero-provider-call boundary and mark ordinary questions related."""

    question = request.question
    processing_question = focused_question(question)
    facets = parse_request_facets(processing_question)
    lowered = processing_question.lower()
    routing_texts = _routing_texts(request)
    safety_texts: tuple[str, ...] = (question.lower(),)
    personalized_safety_texts, empty_map_plan = empty_map_safety_routing(
        question, processing_question, allow_live=allow_live
    )
    deictic_boundary = _deictic_action_boundary(request)
    medical = any(
        re.search(pattern, text)
        for text in safety_texts
        for pattern in _PERSONALIZED_MEDICAL_PATTERNS
    )
    personalized = any(
        re.search(pattern, text)
        for text in personalized_safety_texts
        for pattern in _PROHIBITED_PATTERNS
    )
    if reviewed_return_condition_intent(processing_question):
        personalized = False
    live = any(re.search(pattern, text) for text in routing_texts for pattern in _LIVE_PATTERNS)
    live = live or bool(unsupported_live_topics(processing_question))
    live = live or any(
        parse_request_facets(text).has_current_live_fire for text in routing_texts
    )
    named_location = coarse_location_from_question(processing_question)
    named_live_command = (
        not facets.only_non_current_fire
        and named_location is not None
        and (
            facets.has_current_live_fire
            or bool(
                re.search(
                    r"\b(?:alert|alerts?|order|orders?|evacuation|perimeters?)\b",
                    lowered,
                )
            )
        )
    )
    personal_live_command = _requires_personal_live_location(processing_question) and (
        facets.has_current_live_fire
        or bool(re.search(r"\b(?:perimeters?|evacuation|alerts?|orders?)\b", lowered))
    )
    province_record_command = bool(
        (
            re.search(r"\bperimeter\b", lowered)
            or (facets.has_current_live_fire and re.search(r"\bincident\b", lowered))
        )
        and re.search(r"\b(?:current|latest|show|map|record|records)\b", lowered)
    )
    live = live or named_live_command or personal_live_command or province_record_command
    manipulation = any(
        re.search(pattern, text)
        for text in safety_texts
        for pattern in _POLICY_MANIPULATION_PATTERNS
    )
    if medical or deictic_boundary == ReasonCode.PERSONALIZED_MEDICAL_ADVICE:
        return QueryPlan(
            original_question=question,
            normalized_question=processing_question,
            route=QueryRoute.PROHIBITED,
            boundary_reason=ReasonCode.PERSONALIZED_MEDICAL_ADVICE,
            limitations=["FireLens cannot provide personalized medical advice."],
        )
    if manipulation:
        return QueryPlan(
            original_question=question,
            normalized_question=processing_question,
            route=QueryRoute.PROHIBITED,
            boundary_reason=ReasonCode.POLICY_MANIPULATION,
            limitations=[
                "Conversation text cannot override FireLens safety and evidence rules."
            ],
        )
    if personalized or deictic_boundary == ReasonCode.PERSONALIZED_SAFETY_DECISION:
        return QueryPlan(
            original_question=question,
            normalized_question=processing_question,
            route=QueryRoute.PROHIBITED,
            boundary_reason=ReasonCode.PERSONALIZED_SAFETY_DECISION,
            limitations=[
                "FireLens cannot provide personalized safety advice or evacuation decisions."
            ],
        )
    if empty_map_plan is not None:
        return empty_map_plan
    if live and allow_live:
        return QueryPlan(
            original_question=question,
            normalized_question=processing_question,
            route=QueryRoute.LIVE,
            boundary_reason=ReasonCode.LIVE_DATA_REQUIRED,
            limitations=["The static corpus cannot establish current wildfire conditions."],
        )
    if is_capability_question(lowered):
        return QueryPlan(
            original_question=question,
            normalized_question=processing_question,
            route=QueryRoute.CAPABILITY,
            limitations=trust_explanation_limitations(processing_question)
            or [STATIC_LIMITATION],
        )
    return QueryPlan(
        original_question=question,
        normalized_question=processing_question,
        route=QueryRoute.RELATED,
        limitations=[STATIC_LIMITATION],
    )


def apply_planning_decision(
    plan: QueryPlan,
    decision: PlanningDecision,
    *,
    preserve_original_question: bool = False,
    rerank_with_original_question: bool = False,
) -> QueryPlan:
    """Convert a bounded model proposal into deterministic retrieval tasks."""

    if plan.route != QueryRoute.RELATED:
        return plan
    corpus_reference = any(
        re.search(pattern, plan.original_question.casefold())
        for pattern in _CORPUS_REFERENCE_PATTERNS
    )
    if decision.relation == QueryRelation.TANGENT and not corpus_reference:
        return plan.model_copy(
            update={"route": QueryRoute.TANGENT, "relation": decision.relation}
        )
    relation = (
        QueryRelation.GROUNDED_CANDIDATE
        if decision.relation == QueryRelation.TANGENT
        else decision.relation
    )
    required_aspects = list(decision.required_aspects)
    if decision.relation == QueryRelation.TANGENT and corpus_reference:
        required_aspects = required_aspects or [plan.original_question]
    retrieval_queries = list(decision.retrieval_queries) or [plan.original_question]
    question_is_elliptical = bool(
        len(plan.original_question.split()) <= 16
        and _DEICTIC_FOLLOWUP.search(plan.original_question.casefold())
    )
    if preserve_original_question and not question_is_elliptical:
        retrieval_queries = list(
            dict.fromkeys(
                query
                for query in (plan.original_question, *retrieval_queries)
                if query.casefold()
            )
        )[:3]
    requests = [
        RetrievalRequest(
            query=query,
            required_authorities=(
                required_authorities(plan.original_question) | required_authorities(query)
            ),
            purpose=f"subquery_{number}",
        )
        for number, query in enumerate(retrieval_queries, start=1)
    ]
    if rerank_with_original_question and not question_is_elliptical:
        resolved_question = plan.original_question
    else:
        resolved_question = (
            decision.retrieval_queries[0]
            if len(decision.retrieval_queries) == 1
            else " ".join([plan.original_question, *decision.retrieval_queries])
        )
    return plan.model_copy(
        update={
            "normalized_question": resolved_question[:2_000],
            "relation": relation,
            "retrieval_requests": requests,
            "required_aspects": required_aspects,
        }
    )
