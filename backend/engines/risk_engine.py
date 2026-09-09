"""Local scenario exposure. Radius and scores are explicitly simulated assumptions."""
import json
from pathlib import Path
from engines.resource_engine import haversine_distance

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "habitations.json"


def load_habitations():
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def hazard_radius(incident_type, intensity):
    if intensity <= 0:
        return 0
    maximum = {"flood": 3.5, "landslide": 2, "fire": 1.2, "accident": .2}.get(incident_type.lower(), .2)
    return round(maximum * intensity, 3)


def calculate_habitation_risk(habitation, incident_type, incident_latitude,
                              incident_longitude, hazard_intensity, radius_km=None):
    distance = haversine_distance(incident_latitude, incident_longitude,
                                  habitation["latitude"], habitation["longitude"])
    radius = hazard_radius(incident_type, hazard_intensity) if radius_km is None else radius_km
    exposure = max(0, 1 - (distance / radius) ** 2) if radius > 0 else 0
    susceptibility = habitation.get(f"{incident_type.lower()}_susceptibility", .4)
    susceptibility_score = (.5 + .25 * susceptibility
                            + .15 * habitation["historical_disaster_score"]
                            + .1 * habitation["vulnerability_score"])
    score = round(min(100, 100 * hazard_intensity * susceptibility_score * exposure), 1)
    level, priority = (("RED", "IMMEDIATE") if score >= 75 else
                       ("ORANGE", "SHORT_TERM") if score >= 55 else
                       ("YELLOW", "MEDIUM_TERM") if score >= 25 else ("GREEN", "MONITOR"))
    ratio = round(exposure * hazard_intensity, 4)
    affected = round(habitation["population"] * ratio)
    return {"habitation_id": habitation["id"], "habitation_name": habitation["name"],
            "latitude": habitation["latitude"], "longitude": habitation["longitude"],
            "distance_from_incident_km": round(distance, 2), "risk_score": score,
            "risk_level": level, "relocation_priority": priority,
            "total_population": habitation["population"], "estimated_affected_population": affected,
            "exposure_ratio": ratio,
            "vulnerable_population": {key: habitation[key] for key in ("children", "elderly", "special_assistance")}}


def analyse_habitations(incident_type, incident_latitude, incident_longitude,
                       hazard_intensity, radius_km=None):
    results = [calculate_habitation_risk(h, incident_type, incident_latitude,
                incident_longitude, hazard_intensity, radius_km) for h in load_habitations()]
    results.sort(key=lambda h: h["risk_score"], reverse=True)
    summary = {key: sum(h["estimated_affected_population"] for h in results if h["relocation_priority"] == priority)
               for key, priority in [("immediate_population", "IMMEDIATE"), ("short_term_population", "SHORT_TERM"), ("medium_term_population", "MEDIUM_TERM")]}
    return {"total_habitations": len(results),
            "total_population_requiring_action": summary["immediate_population"] + summary["short_term_population"],
            "priority_summary": summary, "habitations": results,
            "current_radius_km": hazard_radius(incident_type, hazard_intensity) if radius_km is None else radius_km,
            "data_coverage": "LOCAL_DEMO" if any(h["distance_from_incident_km"] < 20 for h in results) else "OUTSIDE_DEMO_AREA",
            "method": "SIMULATED_RADIAL_EXPOSURE"}
