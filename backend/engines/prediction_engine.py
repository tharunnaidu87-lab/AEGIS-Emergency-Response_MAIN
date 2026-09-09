"""Deterministic future footprint and safe staging recommendations."""
import math
from engines.risk_engine import analyse_habitations
from engines.resource_engine import haversine_distance, calculate_resource_requirements


def predict_risk(incident_type, latitude, longitude, intensity, current, people,
                 spreading=False, forecast_minutes=30):
    expanding = incident_type.lower() in {"flood", "fire", "landslide"} and intensity > 0
    growth = (forecast_minutes / 30) * (.6 if spreading else .25) if expanding else 0
    radius = round(current["current_radius_km"] * (1 + growth), 3)
    future_intensity = min(1, intensity + growth * .2)
    future = analyse_habitations(incident_type, latitude, longitude, future_intensity, radius)
    current_by_id = {h["habitation_id"]: h for h in current["habitations"]}
    zones = [{**h, "current_risk_score": current_by_id[h["habitation_id"]]["risk_score"],
              "current_risk_level": current_by_id[h["habitation_id"]]["risk_level"]}
             for h in future["habitations"]]
    new_population = max(0, future["total_population_requiring_action"] - current["total_population_requiring_action"])
    return {"method": "SIMULATED_RULE_BASED", "horizon_minutes": forecast_minutes,
            "current_radius_km": current["current_radius_km"], "future_radius_km": radius,
            "future_intensity": future_intensity, "habitations": zones,
            "additional_population_at_risk": new_population,
            "future_population_requiring_action": future["total_population_requiring_action"],
            "future_resource_requirements": calculate_resource_requirements(incident_type, max(people, new_population)),
            "assumptions": "Radial expansion from supplied intensity and spreading flag; no weather, terrain or official forecast feed."}


def recommend_prepositioning(prediction, spare_resources, latitude, longitude, incident_type):
    targets = [h for h in prediction["habitations"] if h["risk_score"] >= 55
               and h["risk_score"] > h["current_risk_score"]]
    compatible = {"RESCUE_BOAT", "RESCUE_TEAM", "AMBULANCE"} if incident_type.lower() == "flood" else {"FIRE_ENGINE", "RESCUE_TEAM", "AMBULANCE"}
    spare = [r for r in spare_resources if r["type"] in compatible]
    recommendations = []
    for target in targets[:2]:
        if not spare:
            break
        # Stage outside the FUTURE hazard footprint in the direction of the threatened habitation.
        dy = target["latitude"] - latitude
        dx = (target["longitude"] - longitude) * math.cos(math.radians(latitude))
        angle = math.atan2(dy, dx)
        staging_distance = prediction["future_radius_km"] + .5
        stage_lat = latitude + math.sin(angle) * staging_distance / 111.195
        stage_lon = longitude + math.cos(angle) * staging_distance / (111.195 * max(.01, math.cos(math.radians(latitude))))
        unit = min(spare, key=lambda r: haversine_distance(r["latitude"], r["longitude"], stage_lat, stage_lon))
        spare.remove(unit)
        travel = haversine_distance(unit["latitude"], unit["longitude"], stage_lat, stage_lon)
        recommendations.append({"resource_id": unit["id"], "resource_type": unit["type"],
            "zone_id": target["habitation_id"], "zone_name": target["habitation_name"],
            "latitude": stage_lat, "longitude": stage_lon, "eta_minutes": max(1, math.ceil(travel * 2.4)),
            "reason": f"{target['habitation_name']} risk rises from {target['current_risk_score']} to {target['risk_score']}; stage outside the predicted footprint.",
            "status": "RECOMMENDATION", "routing_basis": "DISTANCE_ESTIMATE"})
    return recommendations
