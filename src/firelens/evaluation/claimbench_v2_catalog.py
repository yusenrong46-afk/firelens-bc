"""Author ClaimBench v2 extras once. Do not retune after checker work begins."""

from __future__ import annotations

Q = {
    "zone": "Maintain a non-combustible area extending 1.5 metres around the home.",
    "buffer": "Keep at least 10 metres between woodpiles and the house.",
    "range": "Keep woodpiles between 10 and 30 metres from the house.",
    "cap": "Keep grass no taller than 10 centimetres.",
    "dist": "The recommended travel distance in the guide is 10 kilometres.",
    "time": "Have 72 hours of supplies ready.",
    "height": "Clear branches to 2 metres above the ground.",
    "auth_pbc": "PreparedBC says households should prepare an emergency kit.",
    "auth_bcws": "BC Wildfire Service publishes the provincial fire danger rating.",
    "order": "An evacuation order means you must leave the area immediately.",
    "alert": "An evacuation alert means be ready to leave on short notice.",
    "may_reg": "You may register at the reception centre if you want.",
    "must_reg": "You must register at the reception centre after evacuating.",
    "cond": "If you are on an evacuation alert, prepare your grab-and-go bag.",
    "except_": "Sprinklers help unless water pressure is too low.",
    "stale": "The 2017 plan recommended these routes.",
    "neg": "An evacuation alert does not mean you must leave immediately.",
    "return_": "Do not return home until officials say it is safe.",
    "juris": "This guidance applies in British Columbia.",
    "cached": "Cached records after a refresh failure are not the latest official update.",
    "local": "Your local authority issues the evacuation order for this community.",
    "avoid": "Avoid using garden sprinklers when water pressure is needed for firefighting.",
    "wait": "Wait for an official all-clear before returning.",
    "within": "Stay within the designated reception-centre area.",
    "more": "More than 10 metres of defensible space is recommended around tanks.",
    "kit": "Include water, medication, and copies of important documents.",
    "less": "Keep vegetation less than 10 centimetres tall near the foundation.",
    "beyond": "Store propane beyond 10 metres from the house.",
    "health": "The health authority publishes smoke-health guidance for the public.",
    "mixed": "Some layers are stale after a refresh failure; others were retrieved successfully.",
}


def _case(
    case_id: str, kind: str, dimension: str, quote: str, claim: str, expect: str
) -> dict[str, str]:
    return {
        "id": case_id,
        "kind": kind,
        "dimension": dimension,
        "quote": quote,
        "claim": claim,
        "expect": expect,
    }


def faithful_v2() -> list[dict[str, str]]:
    rows = [
        (
            "G001",
            "unit_alias",
            "zone",
            "Keep a non-combustible area extending 1.5 meters around the home.",
        ),
        (
            "G002",
            "unit_alias",
            "zone",
            "Maintain a non-combustible area extending 1.5 m around the home.",
        ),
        (
            "G003",
            "unit_conversion",
            "zone",
            "Maintain a non-combustible area extending approximately 5 feet around the home.",
        ),
        (
            "G004",
            "unit_conversion",
            "zone",
            "Maintain a non-combustible area of about 4.9 feet around the home.",
        ),
        (
            "G005",
            "comparator_alias",
            "buffer",
            "Keep no less than 10 metres between woodpiles and the house.",
        ),
        (
            "G006",
            "comparator_alias",
            "buffer",
            "Keep a minimum of 10 metres between woodpiles and the house.",
        ),
        (
            "G007",
            "unit_alias",
            "dist",
            "The recommended travel distance in the guide is 10 km.",
        ),
        (
            "G008",
            "unit_conversion",
            "dist",
            "The recommended travel distance in the guide is about 6 miles.",
        ),
        ("G009", "unit_conversion", "time", "Have three days of supplies ready."),
        ("G010", "unit_alias", "cap", "Keep grass no taller than 10 cm."),
        ("G011", "unit_alias", "height", "Clear branches to 2 m above the ground."),
        (
            "G012",
            "authority_preserve",
            "auth_pbc",
            "According to PreparedBC, households should prepare an emergency kit.",
        ),
        (
            "G013",
            "authority_preserve",
            "auth_bcws",
            "BCWS publishes the provincial fire danger rating.",
        ),
        (
            "G014",
            "modality_alias",
            "order",
            "An evacuation order means people are required to leave the area immediately.",
        ),
        (
            "G015",
            "action_preserve",
            "alert",
            "An evacuation alert means being ready to leave on short notice.",
        ),
        (
            "G016",
            "modality_alias",
            "may_reg",
            "Registration at the reception centre is optional.",
        ),
        (
            "G017",
            "modality_alias",
            "must_reg",
            "Registration at the reception centre is mandatory after evacuating.",
        ),
        (
            "G018",
            "condition_preserve",
            "cond",
            "On an evacuation alert, prepare your grab-and-go bag.",
        ),
        (
            "G019",
            "exception_preserve",
            "except_",
            "Sprinklers help except when water pressure is too low.",
        ),
        (
            "G020",
            "negation_preserve",
            "neg",
            "An evacuation alert does not require immediate departure.",
        ),
        (
            "G021",
            "action_preserve",
            "return_",
            "Wait to return home until officials say it is safe.",
        ),
        ("G022", "jurisdiction_preserve", "juris", "This guidance applies in BC."),
        (
            "G023",
            "range_preserve",
            "range",
            "Keep woodpiles from 10 to 30 metres from the house.",
        ),
        (
            "G024",
            "paraphrase",
            "kit",
            "Water, medication, and copies of important documents belong in the kit.",
        ),
        (
            "G025",
            "comparator_alias",
            "buffer",
            "Keep at least 10 m between woodpiles and the house.",
        ),
        (
            "G026",
            "action_preserve",
            "order",
            "Under an evacuation order, leave the area immediately.",
        ),
        ("G027", "unit_preserve", "time", "Have 72-hour supplies ready."),
        ("G028", "freshness_preserve", "stale", "The 2017 plan recommended these routes."),
        (
            "G029",
            "freshness_preserve",
            "mixed",
            "Freshness is mixed: some layers are stale after a refresh failure.",
        ),
        (
            "G030",
            "authority_preserve",
            "auth_pbc",
            "PreparedBC advises households to prepare an emergency kit.",
        ),
        (
            "G031",
            "comparator_alias",
            "more",
            "Greater than 10 metres of defensible space is recommended around tanks.",
        ),
        (
            "G032",
            "comparator_alias",
            "less",
            "Keep vegetation under 10 centimetres tall near the foundation.",
        ),
        (
            "G033",
            "comparator_alias",
            "beyond",
            "Store propane more than 10 metres from the house.",
        ),
        (
            "G034",
            "condition_preserve",
            "avoid",
            "Do not use garden sprinklers when water pressure is needed for firefighting.",
        ),
        ("G035", "action_preserve", "wait", "Return only after an official all-clear."),
        (
            "G036",
            "freshness_preserve",
            "cached",
            "Cached records after a refresh failure are not a current official update.",
        ),
    ]
    if len(rows) != 36:
        raise ValueError(f"expected 36 faithful v2 cases, got {len(rows)}")
    return [
        _case(case_id, "faithful", dimension, Q[quote_key], claim, "accept")
        for case_id, dimension, quote_key, claim in rows
    ]


def mutations_v2() -> list[dict[str, str]]:
    rows = [
        (
            "X001",
            "quantity",
            "zone",
            "Maintain a non-combustible area extending 15 metres around the home.",
        ),
        (
            "X002",
            "unit",
            "zone",
            "Maintain a non-combustible area extending 1.5 feet around the home.",
        ),
        (
            "X003",
            "unit",
            "zone",
            "Maintain a non-combustible area extending approximately 5 metres around the home.",
        ),
        (
            "X004",
            "unit",
            "zone",
            "Maintain a non-combustible area extending 1.5 miles around the home.",
        ),
        ("X005", "unit", "dist", "The recommended travel distance in the guide is 10 miles."),
        ("X006", "unit", "cap", "Keep grass no taller than 10 metres."),
        (
            "X007",
            "unit",
            "zone",
            "Maintain a non-combustible area extending 15 feet around the home.",
        ),
        (
            "X008",
            "quantity",
            "zone",
            "Maintain a non-combustible area extending 15.0 metres around the home.",
        ),
        ("X009", "range", "range", "Keep woodpiles between 1 and 3 metres from the house."),
        ("X010", "unit", "time", "Have 72 minutes of supplies ready."),
        ("X011", "unit", "height", "Clear branches to 2 feet above the ground."),
        ("X012", "unit", "dist", "The recommended travel distance in the guide is 10 metres."),
        (
            "X013",
            "dimension",
            "zone",
            "Maintain a non-combustible area extending 1.5 litres around the home.",
        ),
        (
            "X014",
            "quantity",
            "buffer",
            "Keep at least 100 metres between woodpiles and the house.",
        ),
        ("X015", "unit", "cap", "Keep grass no taller than 10 millimetres."),
        ("X016", "quantity", "height", "Clear branches to 20 metres above the ground."),
        ("X017", "unit", "dist", "The recommended travel distance in the guide is 10 feet."),
        ("X018", "range", "range", "Keep woodpiles between 10 and 300 metres from the house."),
        (
            "X019",
            "comparator",
            "buffer",
            "Keep at most 10 metres between woodpiles and the house.",
        ),
        (
            "X020",
            "comparator",
            "more",
            "Less than 10 metres of defensible space is recommended around tanks.",
        ),
        ("X021", "comparator", "within", "Stay beyond the designated reception-centre area."),
        (
            "X022",
            "comparator",
            "buffer",
            "Keep no more than 10 metres between woodpiles and the house.",
        ),
        (
            "X023",
            "comparator",
            "range",
            "Keep woodpiles outside 10 and 30 metres from the house.",
        ),
        (
            "X024",
            "comparator",
            "less",
            "Keep vegetation more than 10 centimetres tall near the foundation.",
        ),
        ("X025", "comparator", "beyond", "Store propane within 10 metres of the house."),
        ("X026", "comparator", "cap", "Keep grass no shorter than 10 centimetres."),
        (
            "X027",
            "comparator",
            "buffer",
            "Keep fewer than 10 metres between woodpiles and the house.",
        ),
        (
            "X028",
            "comparator",
            "more",
            "No more than 10 metres of defensible space is recommended around tanks.",
        ),
        ("X029", "comparator", "within", "Stay outside the designated reception-centre area."),
        (
            "X030",
            "comparator",
            "range",
            "Keep woodpiles beyond 10 and 30 metres from the house.",
        ),
        (
            "X031",
            "authority",
            "auth_pbc",
            "BC Wildfire Service says households should prepare an emergency kit.",
        ),
        (
            "X032",
            "authority",
            "auth_bcws",
            "Environment Canada publishes the provincial fire danger rating.",
        ),
        (
            "X033",
            "authority",
            "auth_pbc",
            "The municipal fire hall says households should prepare an emergency kit.",
        ),
        (
            "X034",
            "authority",
            "health",
            "EmergencyInfoBC publishes smoke-health guidance for the public.",
        ),
        ("X035", "jurisdiction", "juris", "This guidance applies in Alberta."),
        ("X036", "jurisdiction", "juris", "This guidance applies in Ontario."),
        (
            "X037",
            "authority",
            "auth_bcws",
            "PreparedBC publishes the provincial fire danger rating.",
        ),
        (
            "X038",
            "authority",
            "local",
            "BC Wildfire Service issues the evacuation order for this community.",
        ),
        (
            "X039",
            "authority",
            "auth_pbc",
            "A recognized national weather service says households should prepare an emergency kit.",
        ),
        (
            "X040",
            "authority",
            "kit",
            "Environment Canada says to include water, medication, and copies of important documents.",
        ),
        ("X041", "jurisdiction", "juris", "This guidance applies in Washington State."),
        (
            "X042",
            "authority",
            "auth_bcws",
            "The local government publishes the provincial fire danger rating.",
        ),
        (
            "X043",
            "authority",
            "health",
            "BC Wildfire Service publishes smoke-health guidance for the public.",
        ),
        (
            "X044",
            "jurisdiction",
            "local",
            "A neighbouring province issues the evacuation order for this community.",
        ),
        (
            "X045",
            "authority",
            "auth_pbc",
            "The Canadian Red Cross says households should prepare an emergency kit.",
        ),
        ("X046", "freshness", "stale", "The current plan recommends these routes."),
        ("X047", "freshness", "stale", "The latest plan recommends these routes."),
        (
            "X048",
            "freshness",
            "cached",
            "Cached records after a refresh failure are the latest official update.",
        ),
        ("X049", "freshness", "cached", "These cached records are current conditions."),
        ("X050", "freshness", "mixed", "All layers are current official records."),
        ("X051", "freshness", "mixed", "The latest available picture is fully current."),
        ("X052", "freshness", "stale", "Up-to-date official routes are recommended."),
        ("X053", "freshness", "cached", "Live records after a refresh failure remain current."),
        (
            "X054",
            "freshness",
            "mixed",
            "Unknown freshness still means the records are current.",
        ),
        ("X055", "freshness", "stale", "The 2017 plan is the current official routing advice."),
        (
            "X056",
            "freshness",
            "cached",
            "A failed refresh still provides the latest official update.",
        ),
        ("X057", "freshness", "mixed", "Mixed freshness may be described as fully current."),
        (
            "X058",
            "modality",
            "must_reg",
            "You may register at the reception centre after evacuating.",
        ),
        (
            "X059",
            "modality",
            "may_reg",
            "You must register at the reception centre if you want.",
        ),
        ("X060", "modality", "may_reg", "Registration at the reception centre is mandatory."),
        ("X061", "action", "order", "An evacuation order means you may stay in the area."),
        (
            "X062",
            "action",
            "order",
            "An evacuation order means you can leave the area later today.",
        ),
        ("X063", "action", "alert", "An evacuation alert means leave immediately."),
        ("X064", "action", "wait", "Return before an official all-clear."),
        (
            "X065",
            "action",
            "avoid",
            "Use garden sprinklers when water pressure is needed for firefighting.",
        ),
        ("X066", "action", "return_", "Return home when you believe conditions look safe."),
        (
            "X067",
            "modality",
            "order",
            "An evacuation order means you may leave the area immediately.",
        ),
        ("X068", "action", "alert", "An evacuation alert means wait to pack."),
        ("X069", "modality", "must_reg", "Registration after evacuating is optional."),
        ("X070", "action", "wait", "Act now and return without an official all-clear."),
        ("X071", "action", "order", "An evacuation order means stay at home."),
        (
            "X072",
            "modality",
            "alert",
            "An evacuation alert means you must leave on short notice.",
        ),
        ("X073", "condition", "cond", "Prepare your grab-and-go bag and leave immediately."),
        (
            "X074",
            "exception",
            "except_",
            "Sprinklers help especially when water pressure is too low.",
        ),
        ("X075", "exception", "except_", "Sprinklers help when water pressure is too low."),
        ("X076", "condition", "avoid", "Avoid using garden sprinklers."),
        ("X077", "condition", "cond", "Prepare your grab-and-go bag."),
        ("X078", "condition", "must_reg", "You must register at the reception centre."),
        ("X079", "exception", "except_", "Sprinklers help even if water pressure is too low."),
        ("X080", "condition", "wait", "Wait before returning."),
        ("X081", "condition", "juris", "This guidance applies."),
        ("X082", "condition", "local", "An authority issues the evacuation order."),
        (
            "X083",
            "exception",
            "except_",
            "Sprinklers never help unless water pressure is high.",
        ),
        ("X084", "condition", "cond", "Everyone should prepare a grab-and-go bag."),
        ("X085", "overlap", "neg", "An evacuation alert does mean you must leave immediately."),
        ("X086", "overlap", "return_", "Do return home until officials say it is safe."),
        (
            "X087",
            "overlap",
            "alert",
            "An evacuation alert means be ready to stay on short notice.",
        ),
        (
            "X088",
            "overlap",
            "order",
            "An evacuation order means you must not leave the area immediately.",
        ),
        (
            "X089",
            "overlap",
            "kit",
            "Exclude water, medication, and copies of important documents.",
        ),
        ("X090", "overlap", "wait", "Wait for an official all-clear before leaving."),
        ("X091", "overlap", "neg", "An evacuation alert means you must leave immediately."),
        (
            "X092",
            "authority",
            "auth_bcws",
            "A unnamed provincial office publishes the provincial fire danger rating.",
        ),
        (
            "X093",
            "freshness",
            "cached",
            "Last retrieved cached records are the last officially updated current values.",
        ),
        (
            "X094",
            "unit",
            "zone",
            "Maintain a non-combustible area extending 150 centimetres around the home.",
        ),
        (
            "X095",
            "quantity",
            "buffer",
            "Keep at least 10.0 kilometres between woodpiles and the house.",
        ),
        (
            "X096",
            "modality",
            "more",
            "More than 10 metres of defensible space is required around tanks.",
        ),
    ]
    if len(rows) != 96:
        raise ValueError(f"expected 96 v2 mutations, got {len(rows)}")
    # 150 cm is a valid conversion of 1.5 m; keep it as a mutation of *unit
    # presentation only if we later decide otherwise. Mark X094 as faithful?
    # The required set asks for valid converted equivalent as faithful, so X094
    # must not be an unsafe mutation. Replace it.
    return [
        _case(case_id, "mutation", dimension, Q[quote_key], claim, "reject")
        for case_id, dimension, quote_key, claim in rows
        if case_id != "X094"
    ] + [
        _case(
            "X094",
            "mutation",
            "unit",
            Q["zone"],
            "Maintain a non-combustible area extending 1.5 centimetres around the home.",
            "reject",
        )
    ]


def extra_v2_cases() -> list[dict[str, str]]:
    extras = [*faithful_v2(), *mutations_v2()]
    if len(extras) != 132:
        raise ValueError(f"expected 132 extra v2 cases, got {len(extras)}")
    ids = [case["id"] for case in extras]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate ClaimBench v2 extra ids")
    return extras
