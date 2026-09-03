"""Closed-class vocabulary for the structural place extractor.

These are finite grammatical or geographic inventories (function words,
wildfire-domain nouns, province labels, out-of-province places). They are not
an open-ended blocklist of English words: the extractor rejects spans by
structure, and these sets only mark where a name span ends or what a valid
span must never be geocoded as.
"""

from __future__ import annotations

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

PLACE_ALIASES = {"west k": "West Kelowna"}
