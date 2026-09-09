import json
from pathlib import Path


DATA_FILE = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "relocation_centres.json"
)


def load_relocation_centres():

    with open(DATA_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def calculate_centre_capacity(centre):

    capacities = {
        "space": centre["space_capacity"],
        "water": centre["water_capacity"],
        "food": centre["food_capacity"],
        "sanitation": centre["sanitation_capacity"],
        "medical": centre["medical_capacity"]
    }

    # Find the weakest / limiting capacity
    limiting_factor = min(
        capacities,
        key=capacities.get
    )

    safe_capacity = capacities[limiting_factor]

    available_capacity = max(
        0,
        safe_capacity - centre["current_occupancy"]
    )

    if safe_capacity > 0:

        utilization_percent = round(
            (
                centre["current_occupancy"]
                / safe_capacity
            ) * 100,
            1
        )

    else:
        utilization_percent = 100


    return {
        "id": centre["id"],
        "name": centre["name"],

        "latitude": centre["latitude"],
        "longitude": centre["longitude"],

        "risk_status": centre["risk_status"],

        "safe_carrying_capacity":
            safe_capacity,

        "current_occupancy":
            centre["current_occupancy"],

        "available_capacity":
            available_capacity,

        "limiting_factor":
            limiting_factor,

        "utilization_percent":
            utilization_percent,

        "capacity_breakdown":
            capacities
    }


def calculate_all_centres():

    centres = load_relocation_centres()

    results = []

    for centre in centres:

        capacity_result = calculate_centre_capacity(
            centre
        )

        results.append(
            capacity_result
        )

    return results