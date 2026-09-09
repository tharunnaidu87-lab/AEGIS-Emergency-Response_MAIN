import json
import math
from pathlib import Path


# Path to data/resources.json
DATA_FILE = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "resources.json"
)


def load_resources():
    with open(DATA_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


# ---------------------------------
# DISTANCE BETWEEN TWO GPS POINTS
# ---------------------------------

def haversine_distance(lat1, lon1, lat2, lon2):

    earth_radius = 6371  # kilometres

    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)
    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)

    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(delta_lon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )

    return earth_radius * c


# ---------------------------------
# DETERMINE REQUIRED RESOURCES
# ---------------------------------

def calculate_resource_requirements(
    incident_type,
    people_affected
):

    incident_type = incident_type.lower().strip()

    requirements = {}

    # Accident
    if incident_type in ["accident", "road accident"]:

        requirements["AMBULANCE"] = max(
            1,
            min(4, math.ceil(people_affected / 5))
        )

        requirements["POLICE"] = 1

    # Fire
    elif incident_type == "fire":

        if people_affected >= 20:
            requirements["FIRE_ENGINE"] = 2
        else:
            requirements["FIRE_ENGINE"] = 1

        requirements["AMBULANCE"] = max(
            1,
            min(4, math.ceil(people_affected / 20))
        )

        requirements["POLICE"] = 1

    # Flood
    elif incident_type == "flood":

        requirements["RESCUE_BOAT"] = max(
            1,
            min(4, math.ceil(people_affected / 50))
        )

        requirements["RESCUE_TEAM"] = max(
            1,
            min(3, math.ceil(people_affected / 75))
        )

        requirements["AMBULANCE"] = max(
            1,
            min(3, math.ceil(people_affected / 40))
        )

        requirements["POLICE"] = 1

    # Landslide
    elif incident_type == "landslide":

        requirements["RESCUE_TEAM"] = max(
            1,
            min(3, math.ceil(people_affected / 50))
        )

        requirements["AMBULANCE"] = max(
            1,
            min(3, math.ceil(people_affected / 25))
        )

        requirements["POLICE"] = 1

    # Unknown emergency
    else:

        requirements["AMBULANCE"] = 1
        requirements["POLICE"] = 1

    return requirements


# ---------------------------------
# SELECT NEAREST AVAILABLE UNITS
# ---------------------------------

def allocate_resources(incident_type, people_affected, incident_latitude, incident_longitude,
                       *, unavailable_ids=None, hazard_radius_km=0, severity_score=50,
                       road_blocked=False, response_delay=0):
    unavailable = set(unavailable_ids or [])
    requirements = calculate_resource_requirements(incident_type, people_affected)
    selected, shortages, candidates = [], [], []
    defaults = {"AMBULANCE": 5, "POLICE": 20, "FIRE_ENGINE": 20, "RESCUE_BOAT": 12, "RESCUE_TEAM": 25}
    for original in load_resources():
        resource = original.copy()
        distance = haversine_distance(incident_latitude, incident_longitude,
                                      resource["latitude"], resource["longitude"])
        resource["distance_km"] = round(distance, 2)
        if resource["id"] in unavailable:
            resource["status"] = "BUSY"
        resource["capacity"] = resource.get("capacity", defaults.get(resource["type"], 5))
        resource["eta_minutes"] = max(1, math.ceil(distance * 2.4 * (1.5 if road_blocked else 1) + response_delay))
        # Weighted candidate cost: availability/capability gate, then estimated travel,
        # origin exposure, per-trip capacity and reserve coverage for less urgent incidents.
        resource["origin_risk"] = "EXPOSED" if distance < hazard_radius_km else "CLEAR"
        risk_penalty = 6 if resource["origin_risk"] == "EXPOSED" and resource["type"] != "RESCUE_BOAT" else 0
        reserve_penalty = 5 if resource.get("reserve_for_staging") and severity_score < 80 else 0
        resource["selection_score"] = round(resource["eta_minutes"] + risk_penalty
                                            + reserve_penalty - min(4, resource["capacity"] / 10), 2)
        resource["selection_reason"] = (
            f"Compatible {resource['type']}; {resource['eta_minutes']} min estimated travel; "
            f"capacity {resource['capacity']}; origin {resource['origin_risk'].lower()}; "
            f"weighted cost {resource['selection_score']}."
        )
        resource["routing_basis"] = "DISTANCE_ESTIMATE"
        candidates.append(resource)
    for kind, count in requirements.items():
        available = sorted([r for r in candidates if r["type"] == kind
                            and r["status"] == "AVAILABLE" and r["distance_km"] <= 75],
                           key=lambda r: (r["selection_score"], r["id"]))
        chosen = available[:count]
        selected.extend(chosen)
        if len(chosen) < count:
            shortages.append({"type": kind, "required": count, "available": len(chosen),
                              "shortage": count - len(chosen)})
    selected_ids = {r["id"] for r in selected}
    spare = [r for r in candidates if r["status"] == "AVAILABLE"
             and r["id"] not in selected_ids and r["distance_km"] <= 75]
    return {"required_resources": requirements, "selected_resources": selected,
            "shortages": shortages, "spare_resources": spare, "catalog": candidates,
            "method": "CAPABILITY_AVAILABILITY_ETA_RISK_CAPACITY"}
