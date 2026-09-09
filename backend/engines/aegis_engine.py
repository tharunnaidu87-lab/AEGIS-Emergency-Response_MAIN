"""AEGIS orchestration: one backend result for every role and what-if."""
from time import perf_counter
from engines.severity_engine import calculate_severity
from engines.resource_engine import allocate_resources
from engines.hospital_engine import choose_hospital
from engines.risk_engine import analyse_habitations
from engines.relocation_engine import create_relocation_plan
from engines.confidence_engine import calculate_confidence
from engines.prediction_engine import predict_risk, recommend_prepositioning


def run_aegis_analysis(incident_type, location, latitude, longitude, people_affected,
                       description, hazard_intensity, *, injured=0, trapped=0,
                       vulnerable_groups=None, gps_verified=False, spreading=False,
                       structural_damage=False, scenario=None, unavailable_ids=None,
                       evidence=None):
    options = scenario or {}
    timeline = []

    def stage(name, calculate):
        started = perf_counter()
        value = calculate()
        timeline.append({"stage": name, "status": "COMPLETE",
                         "duration_ms": round((perf_counter() - started) * 1000, 3)})
        return value

    incident = {"type": incident_type, "location": location, "latitude": latitude,
                "longitude": longitude, "reported_people_affected": people_affected,
                "hazard_intensity": hazard_intensity, "description": description,
                "injured": injured, "trapped": trapped}
    stage("INPUT NORMALIZED", lambda: incident)
    confidence = stage("INCIDENT FUSION / EVIDENCE", lambda: calculate_confidence(evidence or [{
        "description": description, "latitude": latitude, "longitude": longitude, "gps_verified": gps_verified}]))
    severity = stage("SEVERITY CALCULATED", lambda: calculate_severity(
        incident_type, people_affected, hazard_intensity, injured, trapped,
        vulnerable_groups, spreading, structural_damage))
    priority = {"score": min(100, round(severity["risk_score"] * .85
                + min(10, people_affected / 10) + min(5, trapped))), "method": "SEVERITY_AND_LIFE_SAFETY"}
    stage("INCIDENT PRIORITIZED", lambda: priority)
    risk = stage("HABITATION RISK", lambda: analyse_habitations(incident_type, latitude, longitude, hazard_intensity))
    unavailable = set(unavailable_ids or []) | set(options.get("unavailable_resource_ids", []))
    resources = stage("RESOURCES OPTIMIZED", lambda: allocate_resources(
        incident_type, people_affected, latitude, longitude, unavailable_ids=unavailable,
        hazard_radius_km=risk["current_radius_km"], severity_score=severity["risk_score"],
        road_blocked=options.get("road_blocked", False),
        response_delay=options.get("response_delay_minutes", 0)))
    prediction = stage("FUTURE RISK PROJECTED", lambda: predict_risk(
        incident_type, latitude, longitude, hazard_intensity, risk, people_affected,
        spreading, options.get("forecast_minutes", 30)))
    # Destinations must be outside the predicted footprint, not merely flagged safe in demo data.
    safe_radius = prediction["future_radius_km"]
    hospital = stage("HOSPITAL SELECTED", lambda: choose_hospital(
        incident_type, max(injured, 1), latitude, longitude,
        hazard_radius_km=safe_radius, capacity_factor=options.get("hospital_capacity_factor", 1),
        response_delay=options.get("response_delay_minutes", 0)))
    relocation_people = risk["total_population_requiring_action"] if incident_type.lower() in {"flood", "landslide", "fire"} else 0
    # Citizen count and modeled habitation exposure describe different populations, not additive totals.
    relocation = stage("SAFE CAPACITY / RELOCATION", lambda: create_relocation_plan(
        relocation_people, latitude, longitude, hazard_radius_km=safe_radius,
        closed_ids=options.get("closed_shelter_ids", []),
        capacity_factor=options.get("shelter_capacity_factor", 1)))
    staging = stage("SPARE STAGING RECOMMENDED", lambda: recommend_prepositioning(
        prediction, resources["spare_resources"], latitude, longitude, incident_type))
    return {"system": "AEGIS", "operational_mode": "EMERGENCY_RESPONSE_AND_RELOCATION" if relocation_people else "EMERGENCY_RESPONSE",
            "incident": incident, "severity_analysis": severity, "confidence_analysis": confidence,
            "priority_analysis": priority, "resource_plan": resources, "hospital_plan": hospital,
            "hazard_analysis": risk, "prediction": prediction, "prepositioning": staging,
            "people_requiring_relocation": relocation_people, "relocation_plan": relocation,
            "pipeline": timeline, "scenario": options,
            "population_basis": "Citizen counts are observations; relocation uses exposed population from the local demo habitation catalogue. They are not added together.",
            "data_sources": {"infrastructure": "LOCAL_DEMO", "forecast": "SIMULATED", "vehicle_positions": "SIMULATED",
                             "resource_eta": "DISTANCE_ESTIMATE", "road_geometry": "OSRM_OR_LABELLED_FALLBACK"}}
