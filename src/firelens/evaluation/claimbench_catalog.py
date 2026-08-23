"""Author the frozen V1.6 ClaimBench catalog once; do not retune after results."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from firelens.evaluation.claimbench import CLAIMBENCH_RELATIVE, MANIFEST_RELATIVE
from firelens.evaluation.common import file_sha256

QUOTES = {
    "kit": "Include water, medication, and copies of important documents.",
    "zone": "Maintain a non-combustible area extending 1.5 metres around the home.",
    "alert": "An evacuation alert means be ready to leave.",
    "order": "An evacuation order means leave the area now.",
    "windows": "If time permits, close all windows before leaving.",
    "return": "Do not return until the evacuation order is rescinded.",
    "date": "The preparedness guide was updated in 2024.",
    "authority": "PreparedBC says households should prepare an emergency kit.",
    "place": "Residents in Kamloops should keep an emergency kit ready.",
    "optional": "Households should keep an emergency kit if they are able.",
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


def _faithful() -> list[dict[str, str]]:
    paraphrases = [
        (
            QUOTES["kit"],
            "A grab-and-go bag should include water, medication, and copies of important documents.",
        ),
        (
            QUOTES["kit"],
            "Reviewed guidance says to include water, medication, and copies of important documents.",
        ),
        (
            QUOTES["kit"],
            "The cited text says to include water, medication, and copies of important documents.",
        ),
        (QUOTES["kit"], "Pack water, medication, and copies of important documents."),
        (QUOTES["kit"], "Important documents, medication, and water belong in the kit."),
        (QUOTES["zone"], "The non-combustible area extends 1.5 m around the home."),
        (QUOTES["zone"], "Keep a non-combustible area extending 1.5 metres around the home."),
        (
            QUOTES["zone"],
            "Maintain a non-combustible area extending 1.5 meters around the home.",
        ),
        (QUOTES["zone"], "A non-combustible area of 1.5 metres should extend around the home."),
        (QUOTES["zone"], "The home should have a 1.5-metre non-combustible area around it."),
        (QUOTES["alert"], "An evacuation alert means people are ready to leave."),
        (QUOTES["alert"], "An evacuation alert means being ready to leave."),
        (QUOTES["alert"], "Be ready to leave when an evacuation alert is issued."),
        (QUOTES["alert"], "An evacuation alert means residents are ready to leave."),
        (QUOTES["alert"], "The cited text says an evacuation alert means be ready to leave."),
        (QUOTES["order"], "An evacuation order means leave the area now."),
        (QUOTES["order"], "An evacuation order means people leave the area now."),
        (QUOTES["order"], "Leave the area now when an evacuation order is in effect."),
        (QUOTES["order"], "The cited text says an evacuation order means leave the area now."),
        (QUOTES["order"], "An evacuation order means leaving the area now."),
        (QUOTES["windows"], "If time permits, close all windows before leaving."),
        (QUOTES["windows"], "When feasible, close all windows before leaving."),
        (QUOTES["windows"], "Close all windows before leaving if time permits."),
        (QUOTES["windows"], "If time permits, all windows should be closed before leaving."),
        (
            QUOTES["windows"],
            "The cited text says to close all windows before leaving if time permits.",
        ),
        (QUOTES["return"], "Do not return until the evacuation order is rescinded."),
        (
            QUOTES["return"],
            "Do not return until the evacuation order is rescinded by officials.",
        ),
        (QUOTES["return"], "People should not return until the evacuation order is rescinded."),
        (
            QUOTES["return"],
            "The cited text says do not return until the evacuation order is rescinded.",
        ),
        (QUOTES["return"], "People should not return until the evacuation order is rescinded."),
        (QUOTES["date"], "The preparedness guide was updated in 2024."),
        (QUOTES["date"], "The guide's preparedness content was updated in 2024."),
        (QUOTES["date"], "Reviewed guidance says the preparedness guide was updated in 2024."),
        (QUOTES["date"], "In 2024, the preparedness guide was updated."),
        (QUOTES["date"], "The 2024 update applies to the preparedness guide."),
        (QUOTES["authority"], "PreparedBC says households should prepare an emergency kit."),
        (
            QUOTES["authority"],
            "PreparedBC says an emergency kit should be prepared by households.",
        ),
        (
            QUOTES["authority"],
            "According to PreparedBC, households should prepare an emergency kit.",
        ),
        (
            QUOTES["authority"],
            "PreparedBC advises that households should prepare an emergency kit.",
        ),
        (QUOTES["authority"], "Households should prepare an emergency kit, PreparedBC says."),
        (QUOTES["place"], "Residents in Kamloops should keep an emergency kit ready."),
        (QUOTES["place"], "In Kamloops, residents should keep an emergency kit ready."),
        (QUOTES["place"], "Kamloops residents should keep an emergency kit ready."),
        (
            QUOTES["place"],
            "Reviewed guidance says residents in Kamloops should keep an emergency kit ready.",
        ),
        (QUOTES["place"], "People in Kamloops should keep an emergency kit ready."),
        (QUOTES["optional"], "Households should keep an emergency kit if they are able."),
        (QUOTES["optional"], "If they are able, households should keep an emergency kit."),
        (QUOTES["optional"], "Households should keep an emergency kit when they are able."),
        (
            QUOTES["optional"],
            "The cited text says households should keep an emergency kit if they are able.",
        ),
        (QUOTES["optional"], "Households should keep an emergency kit if able."),
    ]
    if len(paraphrases) != 50:
        raise ValueError(f"expected 50 faithful paraphrases, got {len(paraphrases)}")
    return [
        _case(f"F{index:03d}", "faithful", "paraphrase", quote, claim, "accept")
        for index, (quote, claim) in enumerate(paraphrases, start=1)
    ]


def _repeat(dimension: str, quote: str, template: str) -> list[tuple[str, str, str]]:
    return [(dimension, quote, template.format(n=index)) for index in range(1, 11)]


def _mutations() -> list[dict[str, str]]:
    places = (
        "Kelowna",
        "Prince George",
        "Victoria",
        "Nanaimo",
        "Cranbrook",
        "Terrace",
        "Penticton",
        "Vernon",
        "Kamloops Junction",
        "Williams Lake",
    )
    years = ("2025", "2023", "2022", "2021", "2020", "2019", "2018", "2016", "2015", "2010")
    quantities = (
        "15 metres",
        "10 metres",
        "3 metres",
        "2 metres",
        "0.5 metres",
        "150 metres",
        "1.6 metres",
        "15.0 metres",
        "1.5 kilometres",
        "1.5 centimetres",
    )
    authorities = (
        "FireSmart BC",
        "FireSmart Canada",
        "BC Wildfire Service",
        "BC Centre for Disease Control",
        "EmergencyInfoBC",
        "Government of British Columbia",
        "BCCDC",
        "BCWS",
        "FireSmart BC",
        "EmergencyInfoBC",
    )
    entities = (
        "a Cedar Ridge household radio",
        "the Cedar Ridge kit list",
        "a Northridge household radio",
        "the Northridge household radio checklist",
        "a Redwood emergency beacon",
        "the Redwood emergency beacon list",
        "a Lakeside siren network token",
        "the Lakeside siren network card",
        "Cedar Ridge copies of a radio",
        "a Cedar Ridge beacon beside water",
    )
    units = (
        "kilometres",
        "kilometers",
        "km",
        "centimetres",
        "centimeters",
        "cm",
        "kilometre",
        "centimetre",
        "kilometers",
        "kilometres",
    )
    rows = [
        *_repeat(
            "action_reversal",
            QUOTES["return"],
            "Return before the evacuation order is rescinded ({n}).",
        ),
        *_repeat(
            "urgency", QUOTES["alert"], "An evacuation alert means leave the area now ({n})."
        ),
        *_repeat(
            "alert_order", QUOTES["alert"], "An evacuation order means be ready to leave ({n})."
        ),
        *_repeat(
            "negation",
            QUOTES["return"],
            "Return while the evacuation order is in effect ({n}).",
        ),
        *_repeat(
            "modality", QUOTES["optional"], "Households must keep an emergency kit ({n})."
        ),
        *(
            (
                "quantity",
                QUOTES["zone"],
                f"Maintain a non-combustible area extending {item} around the home.",
            )
            for item in quantities
        ),
        *(
            (
                "authority",
                QUOTES["authority"],
                f"{item} says households should prepare an emergency kit.",
            )
            for item in authorities
        ),
        *(
            (
                "location",
                QUOTES["place"],
                f"Residents in {item} should keep an emergency kit ready.",
            )
            for item in places
        ),
        *(
            ("date", QUOTES["date"], f"The preparedness guide was updated in {item}.")
            for item in years
        ),
        *_repeat("condition", QUOTES["windows"], "Close all windows ({n})."),
        *(
            (
                "stale_current",
                QUOTES["date"],
                f"The preparedness guide is currently being updated in {item}.",
            )
            for item in years
        ),
        *(
            ("unsupported_entity", QUOTES["kit"], f"Include water, medication, and {item}.")
            for item in entities
        ),
        *_repeat(
            "leave_stay", QUOTES["order"], "An evacuation order means stay at home ({n})."
        ),
        *_repeat(
            "polarity",
            QUOTES["return"],
            "Go back before the evacuation order is rescinded ({n}).",
        ),
        *(
            (
                "unit",
                QUOTES["zone"],
                f"Maintain a non-combustible area extending 1.5 {item} around the home.",
            )
            for item in units
        ),
    ]
    if len(rows) != 150:
        raise ValueError(f"expected 150 mutations, got {len(rows)}")
    return [
        _case(f"U{index:03d}", "mutation", dimension, quote, claim, "reject")
        for index, (dimension, quote, claim) in enumerate(rows, start=1)
    ]


def write_claimbench(repository_root: Path) -> dict[str, object]:
    catalog = {
        "schema_version": "firelens_claimbench.v1",
        "catalog_id": "firelens_claimbench_v1_6",
        "cases": [*_faithful(), *_mutations()],
    }
    output = repository_root / CLAIMBENCH_RELATIVE
    manifest = repository_root / MANIFEST_RELATIVE
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        yaml.safe_dump(catalog, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    payload = {
        "catalog_id": "firelens_claimbench_v1_6",
        "path": CLAIMBENCH_RELATIVE,
        "sha256": file_sha256(output),
        "case_count": len(catalog["cases"]),
        "faithful": 50,
        "mutations": 150,
    }
    manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
