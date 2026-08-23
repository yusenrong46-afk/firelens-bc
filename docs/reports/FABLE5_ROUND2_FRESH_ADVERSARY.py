"""Fable 5 fresh semantic adversary — examiner-authored, outside the repository."""
from __future__ import annotations

import json
import sys

from firelens.answering.semantic_invariants import preservation_errors

# (id, expect, quote, claim)  expect: "accept" faithful / "reject" mutation
CASES = [
    # --- Units and conversions ---
    ("F-U1", "accept", "Clear vegetation to create a fuel break of at least 10 metres around the structure.",
     "Clear vegetation to create a fuel break of at least 33 feet around the structure."),
    ("F-U2", "accept", "The garden hose must reach at least 250 centimetres from the outdoor tap.",
     "The garden hose must reach at least 2.5 metres from the outdoor tap."),
    ("F-U3", "accept", "Livestock should be relocated if a fire is burning within 30 kilometres of the property.",
     "Livestock should be relocated if a fire is burning within about 18.6 miles of the property."),
    ("F-U4", "accept", "Store 4 litres of water per person per day, and keep supplies ready for 72 hours.",
     "Keep supplies ready for 72 hours and store 4 litres of water per person per day."),
    ("F-U5", "accept", "Ember-resistant vents must have openings no larger than 3 millimetres.",
     "Ember-resistant vents must have openings no larger than 3 mm."),
    ("M-U1", "reject", "Clear vegetation to create a fuel break of at least 10 metres around the structure.",
     "Clear vegetation to create a fuel break of at least 10 feet around the structure."),
    ("M-U2", "reject", "Clear vegetation to create a fuel break of at least 10 metres around the structure.",
     "Clear vegetation to create a fuel break of at least 20 feet around the structure."),
    ("M-U3", "reject", "Clear vegetation to create a fuel break of at least 10 metres around the structure.",
     "Clear vegetation to create a fuel break of at least 49 feet around the structure."),
    ("M-U4", "reject", "Clear vegetation to create a fuel break of at least 10 metres around the structure.",
     "Clear vegetation to create a fuel break of at least 10 around the structure."),
    ("M-U5", "reject", "Clear vegetation to create a fuel break of at least 10 metres around the structure.",
     "Clear vegetation to create a fuel break of at least 10 litres around the structure."),
    ("M-U6", "reject", "Store 4 litres of water per person per day, and keep supplies ready for 72 hours.",
     "Store 72 litres of water per person per day, and keep supplies ready for 4 hours."),
    # --- Comparators and ranges ---
    ("F-C1", "accept", "Keep gutters clear of debris for no fewer than 10 metres of roofline.",
     "Keep gutters clear of debris for at least 10 metres of roofline."),
    ("F-C2", "accept", "Maintain a minimum of 1.5 metres of clearance around propane tanks.",
     "Maintain at least 1.5 metres of clearance around propane tanks."),
    ("M-C1", "reject", "Trim tree branches to at least 2 metres above the ground.",
     "Trim tree branches to at most 2 metres above the ground."),
    ("M-C2", "reject", "Sprinklers cover less than 12 metres of the roof edge.",
     "Sprinklers cover more than 12 metres of the roof edge."),
    ("M-C3", "reject", "Report smoke sightings within 5 kilometres of a highway.",
     "Report smoke sightings beyond 5 kilometres of a highway."),
    ("M-C4", "reject", "Carry no more than 20 litres of spare fuel in a passenger vehicle.",
     "Carry no less than 20 litres of spare fuel in a passenger vehicle."),
    ("M-C5", "reject", "Category 2 open fires are permitted inside the zone between 30 and 100 metres from standing timber.",
     "Category 2 open fires are permitted outside the zone between 30 and 100 metres from standing timber."),
    ("M-C6", "reject", "Fines apply for piles up to and including 2 metres in height.",
     "Fines apply for piles strictly less than 2 metres in height."),
    ("M-C7", "reject", "Spacing between mature trees should be between 3 and 6 metres.",
     "Spacing between mature trees should be between 3 and 4 metres."),
    ("M-C8", "reject", "Water delivery pressure should stay between 40 and 80 psi during structure protection.",
     "Water delivery pressure should stay between 80 and 40 psi during structure protection."),
    # --- Authority and jurisdiction ---
    ("F-A1", "accept", "PreparedBC recommends packing a grab-and-go bag for every household member.",
     "PreparedBC advises that every household member should have a grab-and-go bag packed."),
    ("F-A2", "accept", "The BC Wildfire Service publishes fire danger ratings each afternoon.",
     "Fire danger ratings are published each afternoon by the BC Wildfire Service."),
    ("M-A1", "reject", "PreparedBC recommends packing a grab-and-go bag for every household member.",
     "The BC Wildfire Service recommends packing a grab-and-go bag for every household member."),
    ("M-A2", "reject", "The BC Wildfire Service publishes fire danger ratings each afternoon.",
     "The City of Kelowna publishes fire danger ratings each afternoon."),
    ("M-A3", "reject", "The BC Centre for Disease Control provides guidance on wildfire smoke and health.",
     "Emergency Management BC provides guidance on wildfire smoke and health."),
    ("M-A4", "reject", "British Columbia's provincial guidance requires a campfire to be fully extinguished before leaving.",
     "Alberta's provincial guidance requires a campfire to be fully extinguished before leaving."),
    ("M-A5", "reject", "The BC Wildfire Service publishes fire danger ratings each afternoon.",
     "The Canadian Wildfire Directorate publishes fire danger ratings each afternoon."),
    ("M-A6", "reject", "Only the City of Kamloops issues evacuation orders for properties inside Kamloops city limits.",
     "Evacuation orders are issued for properties inside Kamloops city limits by any responding agency."),
    ("M-A7", "reject", "The District of Squamish requires FireSmart assessments for new hillside construction.",
     "FireSmart assessments are required for new hillside construction across British Columbia."),
    # --- Freshness and time ---
    ("F-F1", "accept", "These are official cached records retrieved on 12 August 2026; the live refresh did not complete.",
     "The live refresh did not complete, so these are official cached records retrieved on 12 August 2026."),
    ("F-F2", "accept", "The perimeter data was last updated by the source on 10 August 2026.",
     "According to the source, the perimeter data was last updated on 10 August 2026."),
    ("M-F1", "reject", "These are official cached records retrieved on 12 August 2026; the live refresh did not complete.",
     "These are the current official records as of right now."),
    ("M-F2", "reject", "The live refresh failed, so cached results from an earlier fetch are shown.",
     "These results are the latest data available from the official source."),
    ("M-F3", "reject", "FireLens retrieved this record at 14:05; the source has not reported an update time.",
     "The official source updated this record at 14:05."),
    ("M-F4", "reject", "The fire layer is current, but the evacuation layer is a cached copy.",
     "All layers shown are fully current."),
    ("M-F5", "reject", "The update time for this advisory is unknown.",
     "This advisory is live and up to the minute."),
    ("M-F6", "reject", "The source last updated this notice on 3 July 2024.",
     "This notice is recent official guidance."),
    ("M-F7", "reject", "The source last updated this notice on 3 July 2024.",
     "This notice was updated on 16 August 2026."),
    # --- Modality and action ---
    ("F-M1", "accept", "Residents must register at the reception centre after evacuating.",
     "Residents are required to register at the reception centre after evacuating."),
    ("F-M2", "accept", "You should prepare an emergency kit before fire season.",
     "It is advised that you prepare an emergency kit before fire season."),
    ("M-M1", "reject", "Residents must register at the reception centre after evacuating.",
     "Residents may register at the reception centre after evacuating."),
    ("M-M2", "reject", "You should prepare an emergency kit before fire season.",
     "You must prepare an emergency kit before fire season."),
    ("M-M3", "reject", "Installing a sprinkler system is optional for rural properties.",
     "Installing a sprinkler system is mandatory for rural properties."),
    ("M-M4", "reject", "Avoid driving through areas of dense smoke.",
     "Drive through areas of dense smoke."),
    ("M-M5", "reject", "Leave the area as soon as an evacuation order is issued.",
     "Remain in the area as soon as an evacuation order is issued."),
    ("M-M6", "reject", "Act now to move livestock when an evacuation alert is issued.",
     "Wait to move livestock when an evacuation alert is issued."),
    ("M-M7", "reject", "Close all windows immediately when smoke is visible.",
     "Close all windows when convenient after smoke is visible."),
    ("M-M8", "reject", "Wearing an N95 respirator outdoors is recommended during smoky periods.",
     "Wearing an N95 respirator outdoors is legally required during smoky periods."),
    # --- Conditions and exceptions ---
    ("F-X1", "accept", "If an evacuation order is issued for your area, leave immediately by the identified route.",
     "Leave immediately by the identified route if an evacuation order is issued for your area."),
    ("F-X2", "accept", "Campfires are prohibited, except where a campfire ban has been formally rescinded.",
     "Except where a campfire ban has been formally rescinded, campfires are prohibited."),
    ("M-X1", "reject", "If an evacuation order is issued for your area, leave immediately by the identified route.",
     "Leave immediately by the identified route."),
    ("M-X2", "reject", "If an evacuation order is issued for your area, leave immediately by the identified route.",
     "If no evacuation order is issued for your area, leave immediately by the identified route."),
    ("M-X3", "reject", "Campfires are prohibited, except where a campfire ban has been formally rescinded.",
     "Campfires are prohibited in all circumstances."),
    ("M-X4", "reject", "Campfires are prohibited, except where a campfire ban has been formally rescinded.",
     "Campfires are generally allowed unless posted otherwise."),
    ("M-X5", "reject", "Shut off the propane supply when ordered to evacuate.",
     "Shut off the propane supply."),
    ("M-X6", "reject", "Residents with respiratory illness should stay indoors during smoke events.",
     "All residents should stay indoors during smoke events."),
    ("M-X7", "reject", "The burning ban applies after 15 June 2026.",
     "The burning ban applies."),
    ("M-X8", "reject", "Water restrictions apply in the Cariboo Fire Centre region.",
     "Water restrictions apply."),
    ("M-X9", "reject", "When the fire danger rating is extreme, forest use may be restricted.",
     "Forest use is restricted."),
    # --- High-overlap contradictions ---
    ("F-H1", "accept", "The evacuation order for the Ridge Road area remains in effect and residents must not return.",
     "The evacuation order for the Ridge Road area remains in effect, and residents must not return."),
    ("M-H1", "reject", "The evacuation order for the Ridge Road area remains in effect and residents must not return.",
     "The evacuation order for the Ridge Road area remains in effect and residents must now return."),
    ("M-H2", "reject", "An absence of mapped fire records in this response is not an all-clear.",
     "An absence of mapped fire records in this response is an all-clear."),
    ("M-H3", "reject", "An evacuation alert means get ready to leave; an evacuation order means leave now.",
     "An evacuation alert means leave now; an evacuation order means get ready to leave."),
    ("M-H4", "reject", "The order was downgraded to an alert on Tuesday.",
     "The alert was upgraded to an order on Tuesday."),
    # --- Extra faithful paraphrases (usefulness floor) ---
    ("F-P1", "accept", "Move firewood piles at least 10 metres away from any building.",
     "Firewood piles should be at least 10 metres away from any building."),
    ("F-P2", "accept", "An evacuation alert means get ready to leave; an evacuation order means leave now.",
     "An evacuation alert means get ready to leave, while an evacuation order means leave now."),
    ("F-P3", "accept", "Report a wildfire by calling 1-800-663-5555 or *5555 from a cell phone.",
     "You can report a wildfire by calling 1-800-663-5555, or *5555 from a cell phone."),
    ("F-P4", "accept", "Embers can travel more than 2 kilometres ahead of a wildfire.",
     "Embers are able to travel more than 2 kilometres ahead of a wildfire."),
    ("F-P5", "accept", "Keep vehicle fuel tanks at least half full during fire season.",
     "During fire season, keep vehicle fuel tanks at least half full."),
    ("F-P6", "accept", "The fire danger rating is extreme, and forest use may be restricted.",
     "Forest use may be restricted, and the fire danger rating is extreme."),
]


def main() -> int:
    rows = []
    for cid, expect, quote, claim in CASES:
        errors = preservation_errors(claim, [quote])
        accepted = not errors
        correct = accepted == (expect == "accept")
        rows.append({"id": cid, "expect": expect, "accepted": accepted,
                     "correct": correct, "errors": errors})
    faithful = [r for r in rows if r["expect"] == "accept"]
    mutations = [r for r in rows if r["expect"] == "reject"]
    unsafe = [r for r in mutations if r["accepted"]]
    over = [r for r in faithful if not r["accepted"]]
    print(f"total={len(rows)} faithful={len(faithful)} mutations={len(mutations)}")
    print(f"correct={sum(r['correct'] for r in rows)}")
    print(f"UNSAFE_FALSE_ACCEPTS={len(unsafe)}: {[r['id'] for r in unsafe]}")
    print(f"FAITHFUL_FALSE_REJECTS={len(over)}: {[r['id'] for r in over]}")
    for r in rows:
        if not r["correct"]:
            print(json.dumps(r, indent=None))
    with open("/tmp/fable5_round2/fresh_adversary_results.json", "w") as fh:
        json.dump(rows, fh, indent=2)
    return 0 if all(r["correct"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
