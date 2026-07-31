"""Deterministic high-risk and capability routing.

Only decisions that must never depend on a model live here.  Ordinary questions
continue to the bounded conversational planner instead of being rejected by a
small domain-keyword list.
"""

from __future__ import annotations

import re

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

_PROHIBITED_PATTERNS = (
    r"\b(safest|best)\s+(?:(?:evacuation|escape)\s+)?(road|route|way)\b",
    r"\bwhich\s+(road|route)\s+should\s+(?:i|we)\s+take\b",
    r"\b(am i|are we|is it)\s+safe\b",
    r"\bis\s+(?:my|our)\s+.{0,40}\bsafe\b",
    r"\bshould\s+(?:i|we)\s+(stay|leave|evacuate|return)\b",
    r"\b(?:can|could|may)\s+(?:i|we)\s+safely\s+(?:stay|leave|evacuate|return)\b",
    r"\bwhether\s+(?:my|our)\s+.{0,40}\bsafe\b",
    r"\btell me\s+whether\s+to\s+evacuate\b",
    r"\bshould\s+(?:my|our)\s+family\s+(?:stay|leave|evacuate|return)\b",
    r"\b(?:can|could|may)\s+(?:i|we)\s+(?:return|go back)\s+home\b",
    r"\b(?:return|go back)\s+home\s+(?:yet|now|today|tonight)\b",
    r"\b(?:are|is)\s+(?:i|we|my family|our family)\s+okay\s+to\s+(?:wait|stay|leave|evacuate|return)\b",
    r"\b(?:decide|tell me)\s+(?:if|whether)\s+(?:i|we)\s+(?:stay|leave|evacuate|return)\b",
    r"\bwhether\s+(?:i|we)\s+should\s+(?:stay|leave|evacuate|return)\b",
    r"\bshould\s+(?:i|we)\s+go\s+(?:now|today|tonight|this morning|this afternoon|this evening)\b",
    r"\b(?:my|our)\s+(?:address|street|property|home)\b.{0,50}\b\d{1,6}\b.{0,40}\b(?:under|in)\s+(?:an?\s+)?(?:evacuation\s+)?(?:alert|order)\b",
    r"\b(?:decide|choose|recommend)\b.{0,80}\b(?:evacuat(?:e|ion)|shelter(?:-in-place)?|stay|leave)\b.{0,30}\b(?:versus|vs\.?|or)\b",
    r"\b(?:rank|prioriti[sz]e|compare)\b.{0,80}\b(?:roads?|routes?|highways?)\b.{0,80}\b(?:family|evacuat(?:e|ion)|escape|safest)\b",
    r"\b(?:roads?|routes?|highways?)\b.{0,80}\b(?:rank|priority|safest|best)\b.{0,50}\b(?:family|evacuat(?:e|ion)|escape)\b",
    r"\b(?:authorize|approve|clear)\b.{0,90}\b(?:return(?:ing)?|go back|evacuat(?:e|ion)|stay|leave)\b",
    r"\b(?:exact\s+)?address\s+(?:at\s+)?\d{1,6}\b.{0,100}\b(?:evacuation\s+)?(?:alert|order)\b",
    r"\basap\s+evac(?:uate|uation)?\b",
)

_PERSONALIZED_MEDICAL_PATTERNS = (
    r"\bdiagnos(?:e|is)\b.{0,80}\b(?:me|my|our|whether|cough|symptoms?)\b",
    r"\bprescribe\b.{0,80}\b(?:me|my|for|smoke|headache|cough|medicine|medication)\b",
    r"\bwhat\s+dose\s+of\s+.{0,60}\b(?:safe|take|use|for me)\b",
    r"\bwhat\s+(?:medicine|medication|dose|treatment)\s+should\s+i\b",
    r"\bshould\s+i\s+(?:take|stop taking|use)\s+.{0,50}\b(?:medicine|medication|inhaler)\b",
    r"\bdo\s+i\s+have\s+(?:smoke inhalation|carbon monoxide poisoning|asthma)\b",
    r"\bshould\s+i\s+.{0,50}\b(?:dose|inhaler|medication|medicine)\b",
    r"\b(?:i|my|we|our)\b.{0,80}\b(?:chest (?:pain|hurts?|tightness)|difficulty breathing|shortness of breath|wheez(?:e|ing)|faint(?:ed|ing)?|dizz(?:y|iness))\b",
    r"\b(?:chest (?:pain|hurts?|tightness)|difficulty breathing|shortness of breath|wheez(?:e|ing))\b.{0,80}\bwhat should (?:i|we) do\b",
    r"\bhow should (?:i|we)\s+(?:treat|manage)\s+(?:my|our|the|this)\b",
    r"\b(?:i|my|me|we|our|us)\b.{0,100}\b(?:treat|manage)\s+(?:my|our|the|this)\s+(?:burn|injury|symptom|headache|cough|pain)\b",
    r"\b(?:my|our|personal)\b.{0,50}\b(?:inhaler|medicine|medication|meds?)\b.{0,60}\b(?:schedule|dose|dosage|frequency|how often)\b",
    r"\b(?:schedule|dose|dosage|frequency|how often)\b.{0,60}\b(?:my|our|personal)\b.{0,40}\b(?:inhaler|medicine|medication|meds?)\b",
    r"\b(?:stop|pause|skip|double|increase|decrease|change)\b.{0,40}\b(?:my|our)\b.{0,40}\b(?:medicine|medication|meds?|inhaler|prescription)\b",
    r"\b(?:is|are)\s+(?:this|my|our|the)\b.{0,80}\b(?:disease|illness|condition|smoke inhalation|asthma|infection)\b.{0,30}\b(?:yes or no|diagnos|from smoke|caused by)\b",
    r"\b(?:yes or no|diagnos)\b.{0,80}\b(?:disease|illness|condition|symptoms?|cough|smoke inhalation)\b",
)

_POLICY_MANIPULATION_PATTERNS = (
    r"\bignore\s+.{0,50}\b(?:safety|evidence|boundary|rules?|instructions?)\b",
    r"\b(?:override|bypass|disable)\s+.{0,40}\b(?:safety|evidence|boundary|rules?)\b",
    r"\buse\s+(?:your\s+)?model memory\b",
    r"\bignore\s+.{0,60}\b(?:official|current|live)[-\s]+(?:information|data|source)\s+requirement\b",
    r"\bignore\s+(?:all\s+)?(?:previous|prior|earlier|system|developer)\s+(?:instructions?|rules?|messages?|prompts?)\b",
    r"\b(?:reveal|print|show|repeat|expose)\b.{0,50}\b(?:hidden|system|developer|internal)\s+(?:instructions?|prompt|messages?|rules?)\b",
    r"\b(?:act|behave|respond)\s+as\s+(?:an?\s+)?(?:unrestricted|uncensored|jailbroken)\b",
    r"\b(?:cite|create|provide|use)\b.{0,50}\b(?:fake|fabricated|invented|nonexistent)\b.{0,50}\b(?:citations?|pages?|sources?|urls?|documents?|evidence)\b",
    r"\b(?:invent|fabricate|forge|make up)\b.{0,60}\b(?:evidence|citation|source|url|document|record|perimeter|status|bulletin)\b",
    r"\bbase64[- ]decode\b.{0,80}\b(?:obey|follow|execute|instruction)\b",
    r"\b(?:roleplay|pretend|act)\b.{0,50}\b(?:bc wildfire service|bcws|emergencyinfo\s*bc|authority|official)\b",
    r"\b(?:say|claim|state)\s+the\s+opposite\b.{0,80}\b(?:order|alert|safe|stay|leave|evacuat)\b",
    r"\b(?:hide|omit|suppress)\b.{0,50}\b(?:other|conflict|disagreement|authority|source|evidence)\b",
    r"\b(?:invent|fabricate|make up)\b.{0,50}\b(?:blended|consensus|compromise)\b.{0,40}\b(?:answer|guidance|recommendation)\b",
)

_CORPUS_REFERENCE_PATTERNS = (
    r"\b(?:document|guide|checklist|source)s?\b.{0,80}\b(?:require|recommend|say|agree|disagree|follow)\b",
    r"\b(?:require|recommend|say|agree|disagree|follow)\b.{0,80}\b(?:document|guide|checklist|source)s?\b",
    r"\bwhat\b.{0,60}\b(?:document|guide|checklist|source)s?\b",
    r"\b(?:require|recommend)\b.{0,100}\b(?:grab-and-go|emergency kit|firesmart|wildfire smoke)\b",
    r"\b(?:grab-and-go|emergency kit|firesmart|wildfire smoke)\b.{0,100}\b(?:require|recommend)\b",
)

_LIVE_PATTERNS = (
    r"\b(?:fires?|wildfires?|evacuat(?:ion|ing)|alerts?|orders?|smoke|air quality|roads?|highways?)\b.{0,60}\b(?:right now|currently|latest|today|tonight|this morning|this afternoon|this evening|this week|at the moment|now)\b",
    r"\b(?:right now|currently|latest|today|tonight|this morning|this afternoon|this evening|this week|at the moment|now)\b.{0,60}\b(?:fires?|wildfires?|evacuat(?:ion|ing)|alerts?|orders?|smoke|air quality|roads?|highways?)\b",
    r"\b(active|current)\s+(fires?|wildfires?|evacuations?|alerts?|orders?|smoke|air quality)\b",
    r"\b(is there|are there)\s+(a\s+)?(fire|wildfire)\b",
    r"\bwhere\s+is\s+the\s+(fire|wildfire)\b",
    r"\bnear\s+(me|my home|my house|my address)\b",
    r"\bhas\s+.*\s+(been evacuated|issued an evacuation)\b",
    r"\bwhat(?:'s| is)\s+(?:the\s+)?(?:wildfire|fire)\s+(?:status|situation)\b",
    r"\bhow many\s+(?:active\s+)?(?:fires|wildfires)\b",
    r"\b(?:evacuation|wildfire|fire|smoke|air quality)\s+(?:map|status|update|updates)\b",
    r"\b(?:fires|wildfires)\b.{0,40}\bburning\b",
    r"\bburning\b.{0,40}\b(?:fires|wildfires)\b",
    r"\b(?:roads?|highways?)\b.{0,40}\b(?:open|closed|closure|blocked)\b",
    r"\b(?:is|are|whether)\s+.{1,60}\b(?:under|on)\s+(?:an?\s+)?evacuation\s+(?:alert|order)\b",
    r"\bdoes\s+.{1,60}\bhave\s+(?:an?\s+)?evacuation\s+(?:alert|order)\b",
    r"\bis\s+(?:there\s+)?(?:an?\s+)?evacuation\s+(?:alert|order)\s+(?:active|in effect)\b",
    r"\b(?:fire|wildfire|evacuation|alert|order|smoke|air quality|road|highway)\b.{0,50}\b(?:active|in effect)\b",
    r"\b(?:what|how)\s+(?:is|are)\s+(?:the\s+)?(?:air quality|smoke conditions?)\b",
    r"\bis\s+(?:it|.{1,50})\s+smoky\b",
    r"\b(?:fires?|wildfires?)\b.{0,60}\b(?:current|updated|up[- ]to[- ]date)\b",
    r"\b(?:emergencyinfo\s*bc|emergencyinfobc|bc wildfire service|bcws)\b.{0,60}\b(?:post(?:ed)?|new|update|latest|today|now)\b",
    r"\b(?:my|our)\s+(?:address|home|property|location)\s+is\s+under\s+(?:an?\s+)?(?:evacuation\s+)?(?:alert|order)\b",
    r"\b(?:is|are)\s+there\s+(?:an?\s+)?(?:evacuation\s+)?(?:alert|order)\s+(?:for|near|around|in)\b",
    r"\bis\s+there\b.{1,60}\b(?:evacuation\s+)?(?:alert|order)\b",
    r"\b(?:fires?|wildfires?)\s+(?:near|around|by)\s+[a-z]",
)

_UNSUPPORTED_LIVE_TOPICS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("air quality", ("air quality", "aqhi", "smoke conditions", "smoky")),
    ("road conditions", ("road", "roads", "highway", "highways", "route closure")),
)

_STATIC_GUIDANCE_TERMS = (
    "prepare",
    "preparedness",
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

_CAPABILITY_PATTERNS = (
    r"^(?:hi|hello|hey|good (?:morning|afternoon|evening))[!., ]*$",
    r"\bwhat (?:can|could) you (?:do|help(?: me)? with)\b",
    r"\b(?:what|which) (?:documents|sources|topics).{0,80}\b(?:collection|know|use|cover)\b",
    r"\b(?:show|give) me (?:a few )?(?:example|sample|suggested) questions\b",
    r"\bhelp me (?:use|understand) firelens\b",
    r"\b(?:do you know anything|what do you know) about\b",
    r"\bwhat (?:parts|areas|aspects|kinds).{0,60}\bfirelens (?:explain|cover|answer)\b",
    r"\bhow do (?:your|firelens) citations work\b",
    r"\bwhat is (?:actually )?inside (?:the )?(?:source )?collection\b",
    r"\b(?:do not|don't) know what is in the collection\b",
    r"\b(?:where|how) should i start\b.{0,40}\b(?:firelens|collection|guidance)\b",
    r"\b(?:kinds|types) of firelens questions\b",
    # A context-free request this short cannot identify a safe retrieval target.
    r"^(?:what\s+now|then\s+what|help|help\s+me|where\s+do\s+i\s+start)[?!. ]*$",
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
    """Use history only for a genuinely elliptical current question.

    This prevents an old live request from poisoning a later, self-contained
    stable-guidance question while still resolving "What about right now?".
    """

    current = focused_question(request.question).lower()
    if len(current.split()) > 16 or not _DEICTIC_FOLLOWUP.search(current):
        return (current,)
    previous = [turn.content for turn in request.history if turn.role == "user"]
    return (current, f"{previous[-1].lower()} {current}") if previous else (current,)


def _deictic_action_boundary(request: QueryRequest) -> ReasonCode | None:
    """Resolve only a narrow "should I do that" high-risk antecedent."""

    if not re.search(
        r"\bshould\s+(?:i|we)\s+(?:do|follow|take|use)\s+(?:that|this|it)\b",
        request.question.lower(),
    ):
        return None
    antecedent = " ".join(turn.content.lower() for turn in request.history[-2:])
    if any(term in antecedent for term in ("dose", "inhaler", "medication", "medicine")):
        return ReasonCode.PERSONALIZED_MEDICAL_ADVICE
    if any(
        term in antecedent
        for term in ("leave", "evacuate", "return", "evacuation route", "which road")
    ):
        return ReasonCode.PERSONALIZED_SAFETY_DECISION
    return None


def required_authorities(question: str) -> frozenset[AuthorityClass]:
    """Infer broad authority needs without forcing a mixed question into one class."""

    lowered = question.lower()
    required: set[AuthorityClass] = set()
    if any(term in lowered for term in ("smoke", "air quality", "health", "asthma")):
        required.add(AuthorityClass.PROVINCIAL_PUBLIC_HEALTH)
    if any(
        term in lowered
        for term in (
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
    if any(
        term in lowered
        for term in ("firesmart", "sprinkler", "home ignition", "combustible", "ember")
    ):
        required.add(AuthorityClass.WILDFIRE_PREPAREDNESS)
    return frozenset(required)


def live_layers_for_question(question: str) -> tuple[LiveResultKind, ...]:
    """Return only official layers that can answer the user's live intent."""

    lowered = question.casefold()
    layers: list[LiveResultKind] = []
    fire_status_requested = any(
        re.search(pattern, lowered)
        for pattern in (
            r"\b(?:active|current|latest)\s+(?:fires?|wildfires?)\b",
            r"\b(?:fire|wildfire)\s+(?:status|situation|map|update|updates|perimeter)\b",
            r"\b(?:is there|are there|where is)\b.{0,30}\b(?:fire|wildfire)\b",
            r"\b(?:fires?|wildfires?)\b.{0,40}\b(?:burning|near|around|in bc|in british columbia)\b",
            r"\b(?:bcws|bc wildfire service)\b.{0,50}\b(?:status|map|update|latest|fire)\b",
        )
    )
    if fire_status_requested:
        layers.extend((LiveResultKind.INCIDENT, LiveResultKind.PERIMETER))
    if any(term in lowered for term in ("evacuation", "alert", "order", "emergencyinfobc")):
        layers.append(LiveResultKind.EVACUATION)
    return tuple(dict.fromkeys(layers))


def unsupported_live_topics(question: str) -> tuple[str, ...]:
    lowered = question.casefold()
    return tuple(
        label
        for label, terms in _UNSUPPORTED_LIVE_TOPICS
        if any(term in lowered for term in terms)
    )


def live_query_requires_location(question: str) -> bool:
    """Require explicit coarse input for localized questions; never infer a place."""

    lowered = question.casefold()
    if any(term in lowered for term in ("near me", "my home", "my house", "my address")):
        return True
    if re.search(r"\b(?:alert|order)\s+(?:for|near|around|in)\s+[a-z]", lowered) or re.search(
        r"\b[a-z][a-z .'-]{1,50}\s+is\s+under\s+(?:an?\s+)?(?:evacuation\s+)?(?:alert|order)\b",
        lowered,
    ):
        return True
    named_status = re.search(
        r"\b(?:is there|are there|any)\s+(?:an?\s+)?([a-z][a-z'-]+)\s+(?:evacuation\s+)?(?:alert|order)\b",
        lowered,
    )
    if named_status is not None and named_status.group(1) not in {"evacuation", "active"}:
        return True
    match = re.search(r"\b(?:near|around|within|in|for)\s+([a-z][a-z .'-]{1,80})", lowered)
    if match is None:
        return False
    place = match.group(1).strip(" .?'")
    return not (
        place.startswith("effect")
        or place.startswith("bc")
        or place.startswith("british columbia")
        or place.startswith("the province")
    )


def static_guidance_fragment(question: str) -> str | None:
    """Keep the user's own stable-guidance clause for a mixed live/static request."""

    fragments = [
        fragment.strip(" ,.?;")
        for fragment in re.split(r"(?:[?;+]|\s+(?:and|also|plus)\s+)", question, flags=re.I)
    ]
    selected = [
        fragment
        for fragment in fragments
        if fragment
        and any(term in fragment.casefold() for term in _STATIC_GUIDANCE_TERMS)
        and not any(re.search(pattern, fragment.casefold()) for pattern in _LIVE_PATTERNS)
    ]
    if not selected:
        return None
    return " and ".join(selected)[:2_000]


def plan_query(request: QueryRequest, *, allow_live: bool = True) -> QueryPlan:
    """Apply the zero-provider-call boundary and mark ordinary questions related."""

    question = request.question
    processing_question = focused_question(question)
    lowered = processing_question.lower()
    routing_texts = _routing_texts(request)
    safety_texts = (question.lower(),)
    deictic_boundary = _deictic_action_boundary(request)
    medical = any(
        re.search(pattern, text)
        for text in safety_texts
        for pattern in _PERSONALIZED_MEDICAL_PATTERNS
    )
    personalized = any(
        re.search(pattern, text) for text in safety_texts for pattern in _PROHIBITED_PATTERNS
    )
    live = any(re.search(pattern, text) for text in routing_texts for pattern in _LIVE_PATTERNS)
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
    if live and allow_live:
        return QueryPlan(
            original_question=question,
            normalized_question=processing_question,
            route=QueryRoute.LIVE,
            boundary_reason=ReasonCode.LIVE_DATA_REQUIRED,
            limitations=["The static corpus cannot establish current wildfire conditions."],
        )
    if any(re.search(pattern, lowered) for pattern in _CAPABILITY_PATTERNS):
        return QueryPlan(
            original_question=question,
            normalized_question=processing_question,
            route=QueryRoute.CAPABILITY,
            limitations=[STATIC_LIMITATION],
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
