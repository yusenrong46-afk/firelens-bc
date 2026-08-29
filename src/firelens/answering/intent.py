"""Deterministic high-risk and capability routing.

Only decisions that must never depend on a model live here.  Ordinary questions
continue to the bounded conversational planner instead of being rejected by a
small domain-keyword list.
"""

from __future__ import annotations

import re

from firelens.answering.capability_intent import is_capability_question
from firelens.answering.intent_automaton import TemporalScope, parse_request_intent
from firelens.answering.intent_conversation import (
    _DEICTIC_FOLLOWUP,
    _deictic_action_boundary,
    _named_individual_fire_request,
    _routing_texts,
    continues_prior_live_place,
    conversation_planning_question,
    explicit_corpus_attribution,
    focused_question,
    prefers_general_background,
    prior_anchor_user_question,
    publication_question,
    resolved_user_question,
    reviewed_guidance_intent,
    skips_provider_planning,
)
from firelens.answering.intent_patterns import (
    _CORPUS_REFERENCE_PATTERNS,
    _PERSONALIZED_MEDICAL_PATTERNS,
    _POLICY_MANIPULATION_PATTERNS,
    _PROHIBITED_PATTERNS,
)
from firelens.answering.intent_safety import (
    empty_map_safety_routing,
    is_empty_map_safety_inference,
    trust_explanation_limitations,
)
from firelens.answering.live_named_fire import extracted_located_fire_name
from firelens.answering.location_intent import (
    asks_for_personal_location,
    coarse_location_from_question,
)
from firelens.answering.request_facets import contents_request_facet
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
from firelens.publication.comparison_targets import alert_order_comparison_targets

__all__ = (
    "conversation_planning_question",
    "continues_prior_live_place",
    "explicit_corpus_attribution",
    "focused_question",
    "prefers_general_background",
    "prior_anchor_user_question",
    "publication_question",
    "resolved_user_question",
    "reviewed_guidance_intent",
    "skips_provider_planning",
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
            # Live road handoffs need an operational status request, not a
            # road noun plus an adjacent explanatory word.  Personalized
            # safe-driving questions are handled separately by safety routing.
            r"\b(?:is|are)\s+(?:the\s+)?(?:roads?|highways?|routes?)\b"
            r"(?:\s+[a-z0-9.'-]+){0,4}\s+\b(?:open|closed|blocked)\b|"
            r"\bare\s+there\s+(?:any\s+)?(?:road|highway|route)\s+"
            r"(?:closures?|blocks?)\b.{0,30}\b(?:near|around|in|on|at)\b|"
            r"\bwhich\s+(?:roads?|highways?|routes?)\s+(?:are\s+)?"
            r"(?:currently\s+|now\s+)?(?:open|closed|blocked)\b|"
            r"\bwhere\s+(?:are\s+)?(?:roads?|highways?|routes?)\s+"
            r"(?:open|closed|blocked)\b|"
            r"\b(?:list|show|display|find|locate|check)\b.{0,20}"
            r"\b(?:road|highway|route)\s+(?:closures?|conditions?|blocks?)\b|"
            r"\b(?:check|find\s+out)\s+(?:if|whether)\s+(?:the\s+)?"
            r"(?:roads?|highways?|routes?)\b(?:\s+[a-z0-9.'-]+){0,4}\s+"
            r"(?:is|are)\s+(?:open|closed|blocked)\b|"
            # A mixed request can omit the leading action verb: "show fires
            # around Prince George and whether Highway 97 is closed" still
            # asks for an operational road-status lookup, not a definition.
            r"\b(?:if|whether)\s+(?:the\s+)?(?:roads?|highways?|routes?)\b"
            r"(?:\s+[a-z0-9.'-]+){0,4}\s+(?:is|are)\s+"
            r"(?:open|closed|blocked)\b|"
            # A request for a personal driving-safety decision is prohibited,
            # but the live coordinator must still own it so it can link the
            # responsible road-conditions service rather than dropping it as
            # an unrelated topic.
            r"\b(?:is\s+it|tell\s+me\s+(?:if|whether))\s+.{0,30}"
            r"\bsafe\s+to\s+(?:drive|travel|go)\b|"
            r"\b(?:current|latest|today|now|right\s+now)\b.{0,35}"
            r"\b(?:road|highway|route)\s+(?:closures?|conditions?|blocks?)\b|"
            r"\b(?:road|highway|route)\s+(?:closures?|conditions?|blocks?)\b"
            r".{0,35}\b(?:current|latest|today|now|right\s+now)\b",
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

_ROAD_EXPLANATORY_INTENT = re.compile(
    r"\b(?:what\s+are\s+(?:the\s+)?(?:road|highway|route)\s+"
    r"(?:closures?|conditions?)|caus(?:e|es|ed|ing)|effect(?:s)?|"
    r"polic(?:y|ies)|common(?:ness)?|frequen(?:cy|t|tly)|histor(?:y|ical)|"
    r"explain(?:ed|ing)?)\b",
    re.IGNORECASE,
)


def request_fragments(question: str) -> tuple[str, ...]:
    """Split top-level request clauses without breaking alert/order definitions."""

    return parse_request_facets(question).clause_texts


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

    parsed = parse_request_intent(question)
    if not parsed.has_live_records and parsed.temporal_scope == TemporalScope.NONCURRENT:
        return ()
    named = extracted_located_fire_name(question)
    original_location = coarse_location_from_question(question)
    if (
        named is None
        and original_location is None
        and re.search(
            r"\b(?:this|that|selected)\s+(?:fire|wildfire|incident|record)\b",
            question,
            re.IGNORECASE,
        )
        and re.search(
            r"\b(?:status|details?|size|large|big|hectares?|source|updated|updates?)\b",
            question,
            re.IGNORECASE,
        )
    ):
        # Deictic attributes must bind to a selected ID, never a province list.
        return ()
    layers = list(parsed.live_layers)
    if named is not None and LiveResultKind.INCIDENT not in layers:
        layers.insert(0, LiveResultKind.INCIDENT)
    if is_empty_map_safety_inference(question):
        # Empty-map all-clear attempts are a safety overlay on the typed parse:
        # fetch every owned official layer so the response can expose the lookup
        # and hand off without inventing an all-clear.
        layers.extend(
            (
                LiveResultKind.INCIDENT,
                LiveResultKind.PERIMETER,
                LiveResultKind.EVACUATION,
            )
        )
    return tuple(dict.fromkeys(layers))


def unsupported_live_topics(question: str) -> tuple[str, ...]:
    fragments = request_fragments(question)
    return tuple(
        label
        for label, pattern in _UNSUPPORTED_LIVE_PATTERNS
        if any(
            pattern.search(fragment)
            and not (
                label == "road conditions"
                and (
                    parse_request_intent(fragment).temporal_scope == TemporalScope.NONCURRENT
                    or _ROAD_EXPLANATORY_INTENT.search(fragment)
                )
            )
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

    return parse_request_intent(question).reviewed_guidance_text


def plan_query(request: QueryRequest, *, allow_live: bool = True) -> QueryPlan:
    """Apply the zero-provider-call boundary and mark ordinary questions related."""

    question = request.question
    processing_question = focused_question(question)
    parsed_intent = parse_request_intent(processing_question)
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
    live = bool(unsupported_live_topics(processing_question))
    live = live or parsed_intent.has_live_records
    live = live or any(parse_request_intent(text).has_live_records for text in routing_texts)
    live = live or _named_individual_fire_request(processing_question)
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
    if prefers_general_background(request):
        return QueryPlan(
            original_question=question,
            normalized_question=processing_question,
            route=QueryRoute.TANGENT,
            relation=QueryRelation.TANGENT,
            limitations=[STATIC_LIMITATION],
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


def reviewed_guidance_plan(plan: QueryPlan) -> QueryPlan:
    """Force grounded corpus retrieval without consulting a provider planner."""

    contents_facet = contents_request_facet(plan.original_question)
    retrieval_query = (
        contents_facet.retrieval_query
        if contents_facet is not None
        else plan.normalized_question
    )
    if (
        contents_facet is None
        and re.search(r"\bpack(?:ing|ed)?\b", plan.original_question, re.IGNORECASE)
        and re.search(r"\bwhat\b", plan.original_question, re.IGNORECASE)
    ):
        retrieval_query = "What belongs in an emergency kit?"
    if len(plan.original_question) <= 160:
        required_aspect = plan.original_question
    elif contents_facet is not None:
        # Keep the same syntactically derived container target used for
        # retrieval. PlanningDecision deliberately caps an aspect at 160
        # characters, so a long preamble must not make this fail closed
        # before retrieval starts.
        required_aspect = contents_facet.retrieval_query
    else:
        # focused_question() has already reduced constructed long-preamble
        # inputs to their final explicit question. Preserve that earlier
        # deterministic behavior for every non-contents guidance request.
        required_aspect = plan.normalized_question
    if len(required_aspect) > 160:
        # QueryPlan accepts a wider normalized question than the planning
        # contract. This final bound prevents a 161--500 character stable-
        # guidance request from raising a schema exception. It is used only
        # after the semantic targets above have been selected.
        required_aspect = required_aspect[:160].rstrip()
    atomic = alert_order_comparison_targets(plan.original_question)
    retrieval_queries = list(dict.fromkeys([retrieval_query, *atomic]))[:3]
    required_aspects = list(atomic) or [required_aspect]
    return apply_planning_decision(
        plan,
        PlanningDecision(
            relation=QueryRelation.GROUNDED_CANDIDATE,
            retrieval_queries=retrieval_queries,
            required_aspects=required_aspects,
            explanation=(
                "A deterministic reviewed-guidance intent used bounded corpus retrieval."
            ),
        ),
    )
