"""Closed-class vocabulary and pure span helpers for the structural place extractor.

These are finite grammatical or geographic inventories (function words,
wildfire-domain nouns, province labels, out-of-province places). They are not
an open-ended blocklist of English words: the extractor rejects spans by
structure, and these sets only mark where a name span ends or what a valid
span must never be geocoded as.
"""

from __future__ import annotations

# Imperative/discourse verbs that introduce response-format instructions rather
# than geography. This is a grammatical class used only at a separated request
# preamble boundary; it is not a general content-word denylist.
DISCOURSE_DIRECTIVE_VERBS = frozenset(
    """
    answer describe display emit explain format give list output print provide
    reply respond return say show state summarize summarise tell translate use write
    """.split()
)

# Closed grammatical vocabulary for a separated response-style or prompt-role
# preamble (``JSON: ...``, ``Answer briefly: ...``, ``System message: ...``).
# A prefix must be composed entirely from this vocabulary before it can be
# discarded; a real target such as ``Show West Kelowna: ...`` therefore keeps
# the name-bearing words and is not mistaken for a pure directive.
RESPONSE_PREAMBLE_WORDS = frozenset(
    """
    a admin all an and as assistant brief briefly bullet bullets compact concise
    context csv currently developer format french important in instruction
    instructions json language lowercase machine markdown me message model new no
    now one only or override plain please previous prior prompt query readable
    response right schema sentence sentences short strict system table text the
    tldr to today translation uppercase user using with word words xml yaml yes
    """.split()
)
RESPONSE_PREAMBLE_MARKERS = frozenset(
    """
    admin assistant brief briefly bullet bullets compact concise context csv
    developer format french important instruction instructions json language
    lowercase machine markdown message model override plain prompt query readable
    response schema sentence sentences short strict system table text tldr
    translation uppercase user word words xml yaml
    """.split()
)


def is_response_preamble(tokens: list[str] | tuple[str, ...]) -> bool:
    """Return whether a separated prefix is wholly response-control language."""

    normalized = tuple(token.casefold().strip(".'") for token in tokens if token)
    if not normalized:
        return False
    remaining = tuple(token for token in normalized if token not in DISCOURSE_DIRECTIVE_VERBS)
    if normalized[0] in DISCOURSE_DIRECTIVE_VERBS:
        return all(token in RESPONSE_PREAMBLE_WORDS for token in remaining)
    return bool(set(normalized) & RESPONSE_PREAMBLE_MARKERS) and all(
        token in RESPONSE_PREAMBLE_WORDS for token in normalized
    )


# Spatial anchors are closed grammatical categories shared by span readers.
STRONG_ANCHORS = frozenset(
    {"near", "around", "round", "nearby", "outside", "beside", "toward", "towards",
     "across", "throughout", "arnd", "nr"}
)  # fmt: skip
WEAK_ANCHORS = frozenset({"in", "at", "by", "from", "on", "into", "through", "along", "past"})
CAPITALIZED_ONLY_ANCHORS = frozenset({"to", "of", "for", "nearest", "closest"})
FOR_PREVIOUS = frozenset(
    {"records", "record", "report", "reports", "summary", "overview", "picture", "update",
     "updates", "map", "status", "situation", "conditions", "outlook", "roster", "news",
     "information", "info", "forecast", "data", "fire", "fires", "wildfire", "wildfires",
     "incident", "incidents", "perimeter", "perimeters", "evacuation", "evacuations",
     "alert", "alerts", "order", "orders", "issued", "declared", "lifted", "rescinded",
     "effect"}
)  # fmt: skip
VERB_ANCHORS = frozenset(
    {"leave", "leaving", "evacuate", "evacuating", "flee", "fleeing", "exit", "visit",
     "visiting", "reach", "reaching", "enter", "entering", "approach", "approaching",
     "threaten", "threatening", "hit", "hitting", "affect", "affecting", "meant", "mean"}
)  # fmt: skip
SENTENCE_MARKERS = frozenset(
    {"did", "does", "do", "is", "are", "was", "were", "will", "would", "can", "could",
     "should", "has", "have", "had"}
)  # fmt: skip
STRENGTHENING_PREVIOUS = frozenset(
    {"close", "closest", "nearest", "next", "north", "south", "east", "west", "outside", "out",
     "heading", "going", "driving", "travelling", "traveling", "flying", "moving", "relocating",
     "evacuating", "up", "over", "down", "back", "here", "live", "living", "based", "staying",
     "located", "visiting", "stuck", "camping", "vacationing", "centre", "center", "focus",
     "zoom", "map", "records", "record", "report", "reports", "summary", "overview", "picture",
     "update", "updates", "status", "situation", "conditions", "outlook", "roster", "news",
     "fire", "fires", "wildfire", "wildfires", "incident", "incidents", "perimeter",
     "perimeters", "evacuation", "evacuations", "alert", "alerts", "order", "orders", "distance"}
)  # fmt: skip
FRONTED_TRAILING_MODIFIERS = frozenset(
    {"area", "currently", "now", "please", "right", "rn", "today", "tonight"}
)


# Function words end a name span. This is a finite grammatical inventory, not
# a content blocklist.
FUNCTION_WORDS = frozenset(
    """
    a an the this that these those my our your his her its their
    i me we us you he she it they them one ones someone anyone everyone
    anything something nothing everything anybody somebody nobody everybody
    here there where when what which who whom whose why how
    is are am was were be been being do does did have has had
    can could may might must shall should will would
    and or but nor so yet if then than because while whether
    not no yes any some all every each either neither both few many much
    more most other another such same own
    in on at by for from to of with without into onto over under above below
    near around round arnd nr about across along through throughout toward towards up down
    out off past beyond amid beside between among against after before during since until
    within outside inside versus vs plus based according regarding concerning per
    please just also only even still already again ever never
    now today tonight currently right rn yesterday tomorrow tonite
    immediately asap quickly soon early late later straight
    very really quite too
    actually anyway basically honestly however instead finally first firstly next
    ok okay sorry thanks hi hello hey wait hmm um well quick urgent
    easier easiest harder hardest simpler simplest shorter longer faster briefer
    effect progress force general particular case fact addition short detail depth
    selected chosen highlighted clicked pinned
    tell show give list find check see look want need know think compare explain
    january february march april may june july august september october november december
    monday tuesday wednesday thursday friday saturday sunday
    moment present minute hour morning afternoon evening night week weekend month year
    summer winter spring fall season day days dawn noon midnight
    pull bring catch display summarize summarise describe get fetch open load refresh
    search locate identify count rank sort filter highlight zoom focus centre center
    move put
    """.split()
)

# Geographic-scope adjectives are not places on their own ("the national
# wildfire situation"), but they do appear inside proper names ("Glacier
# National Park"), so they only reject a span made of nothing else.
SCOPE_ADJECTIVES = frozenset(
    """
    national nationwide nationally provincial provincially regional local global
    international canadian countrywide worldwide federal
    """.split()
)

# Wildfire-domain nouns and generic place nouns end a span too; a place name
# never continues through them.
DOMAIN_NOUNS = frozenset(
    """
    fire fires wildfire wildfires blaze blazes incident incidents perimeter perimeters
    forest grass brush bush structure crown ground surface holdover wildland interface
    campfire campfires bonfire bonfires tactical
    evacuation evacuations evac alert alerts order orders record records roster
    smoke haze map maps layer layers pin pins marker markers
    status size hectares hectare distance km kilometre kilometres kilometer kilometers
    area areas region regions zone zones community communities city cities town towns
    village villages place places neighbourhood neighborhood location locations spot
    home homes property properties
    nearby closest nearest close closer farthest furthest far away
    active current latest official reported listed matching burning available unavailable
    update updates status situation report reports news conditions overview summary
    picture outlook activity info information data feed feeds source sources service
    kit kits bag bags checklist checklists list lists plan plans guidance tips advice
    supplies documents insurance
    risk risks danger dangerous safe unsafe fine rating ratings season ecology history
    safety preparedness
    behaviour behavior prevention cause causes statistics stats science weather forecast
    ban bans restrictions permits smoke-readiness readiness
    geography distribution latitude longitude count counts number numbers type types
    stage stages control name names date dates trend trends total totals note
    start started starting spread spreading grow growing growth contained controlled held
    emergency firelens guide guides manual handbook document documents page site website app
    answer answers question questions instructions schedule
    evidence excerpt excerpts citation citations corpus collection chunk chunks authority
    """.split()
)

# Generic place and dwelling nouns that stand in for the user's own location.
PERSONAL_PLACE_NOUNS = frozenset(
    {"town", "city", "area", "neighbourhood", "neighborhood", "place", "home", "house",
     "houses", "village", "community", "apartment", "condo", "basement", "trailer", "cabin",
     "rv", "campground", "campsite", "hotel", "motel", "building", "flat", "suite", "unit",
     "duplex", "townhouse", "farm", "ranch", "acreage", "property", "school", "work",
     "office", "workplace"}
)  # fmt: skip

# Compass and relative-position adjectives are not places on their own
# ("northern or southern BC"), though they open proper names ("West Kelowna").
DIRECTION_WORDS = frozenset(
    """
    north south east west northern southern eastern western northeast northwest
    southeast southwest central interior coastal upper lower inland
    """.split()
)

LOCALITY_MODIFIERS = frozenset({"downtown", "central", "greater", "metro", "urban", "rural"})
# Words a name may follow without being part of it: "of current Kelowna fires".
SKIPPABLE_LEAD = LOCALITY_MODIFIERS | frozenset(
    {"the", "a", "an", "current", "active", "latest", "ongoing", "recent", "new", "any"}
)
CIVIC_PREFIXES = ("city of", "town of", "district of", "village of", "municipality of")

PROVINCE_LABELS = frozenset(
    {"bc", "b c", "b.c", "b.c.", "british columbia", "the province", "province", "bcws",
     "bc wildfire service"}
)  # fmt: skip

OUT_OF_PROVINCE_PLACES = frozenset(
    {
        "alberta", "saskatchewan", "manitoba", "ontario", "quebec", "new brunswick",
        "nova scotia", "prince edward island", "newfoundland", "newfoundland and labrador",
        "yukon", "northwest territories", "nunavut", "calgary", "edmonton", "banff",
        "jasper", "lethbridge", "red deer", "grande prairie", "fort mcmurray", "toronto",
        "ottawa", "montreal", "winnipeg", "regina", "saskatoon", "whitehorse", "yellowknife",
        "alaska", "washington", "washington state", "oregon", "idaho", "montana",
        "california", "seattle", "portland", "spokane", "bellingham",
    }
)  # fmt: skip

WHOLE_COUNTRY_LABELS = frozenset(
    {"canada", "the rest of canada", "united states", "usa", "us", "america",
     "atlantic", "pacific", "coast", "north america", "nation", "country", "the nation",
     "the country"}
)  # fmt: skip

PLACE_ALIASES = {
    "70 mile house": "70 Mile House",
    "alert bay": "Alert Bay",
    "new denver": "New Denver",
    "new hazelton": "New Hazelton",
    "new westminster": "New Westminster",
    "west k": "West Kelowna",
}


def normalize_question(text: str) -> str:
    """Normalize punctuation and whitespace while preserving place-span offsets."""

    text = text.replace("’", "'").replace("—", " — ").replace("–", " – ")
    return " ".join(text.split())


def stop_key(token: str) -> str:
    """Reduce possessive and dotted tokens to their closed-vocabulary key."""

    return token.casefold().strip(".'").split("'")[0]


def is_stop(token: str) -> bool:
    """Return whether a token terminates a place-name span."""

    lowered = stop_key(token)
    return lowered in FUNCTION_WORDS or lowered in DOMAIN_NOUNS or lowered in VERB_ANCHORS


def merge_overlapping(
    communities: list[tuple[str, int, int]],
) -> list[tuple[str, int, int]]:
    """Collapse overlapping captures, retaining the longer place span."""

    ordered = sorted(communities, key=lambda item: (item[1], -(item[2] - item[1])))
    merged: list[tuple[str, int, int]] = []
    for label, begin, end in ordered:
        if merged and begin < merged[-1][2]:
            if end - begin > merged[-1][2] - merged[-1][1]:
                merged[-1] = (label, begin, end)
            continue
        merged.append((label, begin, end))
    return merged
