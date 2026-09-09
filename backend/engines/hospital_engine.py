import json
from pathlib import Path

from engines.resource_engine import haversine_distance


DATA_FILE = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "hospitals.json"
)


def load_hospitals():

    with open(DATA_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def choose_hospital(incident_type, people_affected, incident_latitude, incident_longitude,
                    *, hazard_radius_km=0, capacity_factor=1, response_delay=0):
    suitable, excluded = [], []
    for original in load_hospitals():
        h = original.copy()
        distance = haversine_distance(incident_latitude, incident_longitude, h["latitude"], h["longitude"])
        h["available_beds"] = int(h["available_beds"] * capacity_factor)
        h["icu_beds"] = min(h["available_beds"], int(h["icu_beds"] * capacity_factor))
        reason = None
        if h["status"] != "AVAILABLE" or h["available_beds"] <= 0:
            reason = "No available capacity"
        elif distance <= hazard_radius_km:
            reason = "Inside predicted hazard footprint"
        elif distance > 75:
            reason = "Outside local service range"
        elif incident_type.lower() in {"accident", "road accident", "building collapse", "landslide"} and not h["trauma_center"]:
            reason = "Trauma capability required"
        elif incident_type.lower() == "fire" and not h["burn_unit"]:
            reason = "Burn capability required"
        if reason:
            excluded.append({"id": h["id"], "reason": reason})
            continue
        h["distance_km"] = round(distance, 2)
        h["eta_minutes"] = max(1, round(distance * 2.4 + response_delay))
        h["selection_score"] = round(h["eta_minutes"] + max(0, people_affected - h["available_beds"]) * 2
                                      - min(h["available_beds"] / 20, 2) - (1 if h["icu_beds"] else 0), 2)
        h["reason"] = f"Outside predicted hazard; required treatment capability; {h['available_beds']} demo beds; {h['eta_minutes']} min distance-based ETA."
        h["capacity_shortfall"] = max(0, people_affected - h["available_beds"])
        h["routing_basis"] = "DISTANCE_ESTIMATE"
        suitable.append(h)
    suitable.sort(key=lambda h: (h["selection_score"], h["id"]))
    return {"selected_hospital": suitable[0] if suitable else None,
            "alternatives": suitable[1:3], "excluded": excluded,
            "message": "Treatment recommendation; demo capacity is not a reservation." if suitable else "No suitable safe hospital in local demo data"}
