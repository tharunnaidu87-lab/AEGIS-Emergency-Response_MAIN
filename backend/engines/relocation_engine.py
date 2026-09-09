from engines.capacity_engine import calculate_all_centres
from engines.resource_engine import haversine_distance


def create_relocation_plan(people_to_relocate, incident_latitude, incident_longitude,
                           *, hazard_radius_km=0, closed_ids=None, capacity_factor=1):
    if people_to_relocate < 0:
        raise ValueError("Population cannot be negative")
    suitable, excluded = [], []
    for original in calculate_all_centres():
        centre = original.copy()
        distance = haversine_distance(incident_latitude, incident_longitude,
                                      centre["latitude"], centre["longitude"])
        centre["safe_carrying_capacity"] = int(centre["safe_carrying_capacity"] * capacity_factor)
        centre["available_capacity"] = max(0, centre["safe_carrying_capacity"] - centre["current_occupancy"])
        if (centre["risk_status"] != "SAFE" or centre["id"] in (closed_ids or [])
                or distance <= hazard_radius_km or distance > 75 or not centre["available_capacity"]):
            excluded.append({"id": centre["id"], "name": centre["name"],
                             "reason": "Unsafe, closed, exposed, outside range or no remaining capacity"})
            continue
        centre["distance_km"] = round(distance, 2)
        suitable.append(centre)
    suitable.sort(key=lambda c: (c["distance_km"], c["id"]))
    remaining = people_to_relocate
    assignments = []
    for centre in suitable:
        if remaining <= 0:
            break
        available = centre["available_capacity"]
        allocated = min(available, remaining)
        assignments.append({"centre_id": centre["id"], "centre_name": centre["name"],
            "latitude": centre["latitude"], "longitude": centre["longitude"],
            "distance_km": centre["distance_km"], "safe_carrying_capacity": centre["safe_carrying_capacity"],
            "current_occupancy": centre["current_occupancy"], "available_before_allocation": available,
            "people_allocated": allocated, "remaining_capacity_after": available - allocated,
            "limiting_factor": centre["limiting_factor"], "routing_basis": "DISTANCE_ESTIMATE"})
        remaining -= allocated
    allocated = people_to_relocate - remaining
    return {"people_requiring_relocation": people_to_relocate, "total_allocated": allocated,
            "unallocated_people": remaining, "coverage_percent": round(allocated / people_to_relocate * 100, 1) if people_to_relocate else 100,
            "relocation_status": "FULLY_ALLOCATED" if not remaining else "PARTIALLY_ALLOCATED" if allocated else "NO_SAFE_CAPACITY",
            "assignments": assignments, "excluded_centres": excluded,
            "allocation_basis": "PER_INCIDENT_PLANNING_NOT_RESERVATION"}
