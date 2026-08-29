"""Deterministic routing pattern tables. Imported by intent.py."""

from __future__ import annotations

import re

_PROHIBITED_PATTERNS = (
    r"\b(safest|best)\s+(?:(?:evacuation|escape)\s+)?(road|route|way|highway)\b",
    r"\bwhich\s+(road|route)\s+should\s+(?:i|we)\s+take\b",
    r"\bwhat\s+(?:road|route|way|highway)\s+should\s+"
    r"(?:(?:my|our)\s+)?(?:family|household|i|we)\s+take\b",
    r"\b(am i|are we|is it)\s+safe\b",
    r"\bis\s+(?:my|our)\s+.{0,40}\bsafe\b",
    r"\bshould\s+(?:i|we)\s+(stay|leave|evacuate|return)\b",
    r"\b(?:can|could|may)\s+(?:i|we)\s+leave\s+"
    r"(?!(?:work|school|home|early|the\s+office|my\s+office)\b)"
    r"[a-z][a-z .'-]{1,60}?\s+(?:right\s+now|now|today|tonight)\b",
    r"\b(?:can|could|may)\s+(?:i|we)\s+safely\s+(?:stay|leave|evacuate|return)\b",
    r"\bwhether\s+(?:my|our)\s+.{0,40}\bsafe\b",
    r"\btell me\s+whether\s+to\s+evacuate\b",
    r"\bshould\s+(?:my|our)\s+family\s+(?:stay|leave|evacuate|return)\b",
    r"\b(?:can|could|may)\s+(?:i|we)\s+(?:return|go back)\s+home\b",
    r"\bis it okay to\s+(?:return|stay|leave|go back|evacuate|drive)\b",
    r"\bokay to return home\b",
    r"\bshould\s+(?:i|we)\s+take\s+(?:that|this|the)\s+(?:road|route|way)\b",
    r"\b(?:if|whether)\s+i\s+am\s+safe\b",
    r"\b(?:if|whether)\s+we\s+are\s+safe\b",
    r"\btell me if\s+(?:i am|i'm|we are)\s+safe\b",
    r"\b(?:return|go back)\s+home\s+(?:yet|now|today|tonight)\b",
    r"\b(?:are|is)\s+(?:i|we|my family|our family)\s+okay\s+to\s+(?:wait|stay|leave|evacuate|return)\b",
    r"\b(?:tell me|decide|say)\s+(?:if|whether)\s+(?:i|we|my|our)\b.{0,40}\bshould\s+(?:stay|leave|evacuate|return)\b",
    r"\btell me\s+(?:i|we|my family|our family)\s+(?:do|does)\s+not\s+need\s+to\s+(?:stay|leave|evacuate|return)\b",
    r"\b(?:decide|tell me)\s+(?:if|whether)\s+(?:i|we)\s+(?:stay|leave|evacuate|return)\b",
    r"\bwhether\s+(?:i|we)\s+should\s+(?:stay|leave|evacuate|return)\b",
    r"\bshould\s+(?:i|we)\s+go\s+(?:now|today|tonight|this morning|this afternoon|this evening)\b",
    r"\b(?:is it|tell me (?:if|whether))\s+.{0,30}\bsafe\s+to\s+(?:drive|travel|go)\b",
    r"\bis\s+(?!a\b|an\b).{1,80}\bsafe(?:\s+(?:right now|today|tonight)|"
    r"\s+from\b.{0,50}|\s+to\s+(?:stay|return|drive|travel)\b.{0,40})?[?!.]*$",
    r"\b(?:can|could|may)\s+(?:people|residents?|famil(?:y|ies)|households?|"
    r"visitors?|(?:the\s+)?community)\s+safely\s+(?:stay|leave|evacuate|return)\b",
    r"\bshould\s+.{0,50}\b(?:people|residents?|famil(?:y|ies)|households?|"
    r"visitors?)\s+(?:safely\s+)?(?:stay|leave|evacuate|return)\b",
    r"\b(?:my|our)\s+(?:address|street|property|home)\b.{0,50}\b\d{1,6}\b.{0,40}\b(?:under|in)\s+(?:an?\s+)?(?:evacuation\s+)?(?:alert|order)\b",
    r"\b(?:decide|choose|recommend)\b.{0,80}\b(?:evacuat(?:e|ion)|shelter(?:-in-place)?|stay|leave)\b.{0,30}\b(?:versus|vs\.?|or)\b",
    r"\b(?:rank|prioriti[sz]e|compare)\b.{0,80}\b(?:roads?|routes?|highways?)\b.{0,80}\b(?:family|evacuat(?:e|ion)|escape|safest)\b",
    r"\b(?:roads?|routes?|highways?)\b.{0,80}\b(?:rank|priority|safest|best)\b.{0,50}\b(?:family|evacuat(?:e|ion)|escape)\b",
    r"\b(?:authorize|approve|clear)\b.{0,90}\b(?:return(?:ing)?|go back|evacuat(?:e|ion)|stay|leave)\b",
    r"\b(?:exact\s+)?address\s+(?:at\s+)?\d{1,6}\b.{0,100}\b(?:evacuation\s+)?(?:alert|order)\b",
    r"\basap\s+evac(?:uate|uation)?\b",
    r"\b(?:am i|are we)\s+under\b",
    r"\bwhich one\s+am i\s+under\b",
)

_PERSONALIZED_ROUTE_REQUEST = re.compile(
    r"\b(?:safest|best)\s+(?:(?:evacuation|escape)\s+)?"
    r"(?:road|route|way|highway)\b|"
    r"\bwhich\s+(?:road|route)\s+should\s+(?:i|we)\s+take\b|"
    r"\bwhat\s+(?:road|route|way|highway)\s+should\s+"
    r"(?:(?:my|our)\s+)?(?:family|household|i|we)\s+take\b",
    re.IGNORECASE,
)


def is_personalized_route_request(question: str) -> bool:
    """True when the user asks FireLens to choose an evacuation route."""

    return _PERSONALIZED_ROUTE_REQUEST.search(question) is not None


_REVIEWED_RETURN_CONDITION_PATTERNS = (
    r"^\s*(?:can|could|may)\s+(?:i|we)\s+(?:return|go back)\s+home\s+"
    r"after\s+an?\s+evacuation[?!.]*\s*$",
    r"^\s*when\s+(?:can|could|may|should)\s+an?\s+evacuated\s+"
    r"(?:resident|person|household|family)\s+(?:return|go back)\s+home\s+"
    r"after\s+an?\s+(?:wildfire|evacuation)[?!.]*\s*$",
)

_RETURN_DECISION_CUE_PATTERNS = (
    r"\b(?:yet|right now|now|today|tonight|currently|active|in effect)\b",
    r"\b(?:this|that|the)\s+(?:evacuation|alert|order)\b",
    r"\b(?:this|that|those|these|there)\b",
    r"\b(?:my|our)\s+(?:address|street|property)\b",
    r"\b\d{1,6}\s+[a-z].{0,40}\b(?:street|st|avenue|ave|road|rd|boulevard|blvd)\b",
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
    r"\b(?:invent|fabricate|forge|make up)\b.{0,80}\b(?:evidence|citations?|sources?|urls?|documents?|records?|perimeters?|status(?:es)?|bulletins?)\b",
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
    r"\b(?:evacuat(?:ion|ing)|alerts?|orders?|smoke|air quality|roads?|highways?)\b.{0,60}\b(?:right now|currently|latest|today|tonight|this morning|this afternoon|this evening|this week|at the moment|now)\b",
    r"\b(?:right now|currently|latest|today|tonight|this morning|this afternoon|this evening|this week|at the moment|now)\b.{0,60}\b(?:evacuat(?:ion|ing)|alerts?|orders?|smoke|air quality|roads?|highways?)\b",
    r"\b(active|current)\s+(evacuations?|alerts?|orders?|smoke|air quality)\b",
    r"\bhas\s+.*\s+(been evacuated|issued an evacuation)\b",
    r"\b(?:evacuation|smoke|air quality)\s+(?:map|status|update|updates)\b",
    r"\b(?:roads?|highways?)\b.{0,40}\b(?:open|closed|closure|blocked)\b",
    r"\b(?:is|are|whether)\s+.{1,60}\b(?:under|on)\s+(?:an?\s+)?evacuation\s+(?:alerts?|orders?)\b",
    r"\bdoes\s+.{1,60}\bhave\s+(?:an?\s+)?evacuation\s+(?:alerts?|orders?)\b",
    r"\bis\s+(?:there\s+)?(?:an?\s+)?evacuation\s+(?:alerts?|orders?)\s+(?:active|in effect)\b",
    r"\b(?:evacuation|alert|order|smoke|air quality|road|highway)\b.{0,50}\b(?:active|in effect)\b",
    r"\b(?:what|how)\s+(?:is|are)\s+(?:the\s+)?(?:air quality|smoke conditions?)\b",
    r"\bis\s+(?:it|.{1,50})\s+smoky\b",
    r"\b(?:emergencyinfo\s*bc|emergencyinfobc)\b.{0,60}\b(?:post(?:ed)?|new|update|latest|today|now)\b",
    r"\b(?:my|our)\s+(?:address|home|property|location)\s+is\s+under\s+(?:an?\s+)?(?:evacuation\s+)?(?:alerts?|orders?)\b",
    r"\b(?:is|are)\s+there\s+(?:an?\s+)?(?:evacuation\s+)?(?:alerts?|orders?)\s+(?:for|near|around|in)\b",
    r"\b(?:is|are)\s+there\b.{1,60}\b(?:evacuation\s+)?(?:alerts?|orders?)\b",
    r"\b(?:current|latest|active|updated)\s+(?:fire\s+|wildfire\s+)?perimeters?\b",
    r"\b(?:show|display|where)\b.{0,40}\b(?:fire\s+|wildfire\s+)?perimeters?\b",
    r"\b(?:show|display|list|map|check|find)\b.{0,80}"
    r"\b(?:(?:evacuation|evac)\s+)?(?:alerts?|orders?)\b",
)
