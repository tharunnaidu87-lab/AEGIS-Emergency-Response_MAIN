"""Transparent prototype score; not a clinical or official hazard scale."""


def calculate_severity(incident_type, people_affected, hazard_intensity=.5,
                       injured=0, trapped=0, vulnerable_groups=None,
                       spreading=False, structural_damage=False):
    factors = {"baseline": 10}
    if incident_type.lower().strip() in {"flood", "fire", "landslide", "building collapse"}:
        factors["hazard_type"] = 15
    factors["people_affected"] = min(25, (10 if people_affected >= 10 else 0)
                                    + (8 if people_affected >= 50 else 0)
                                    + (7 if people_affected >= 100 else 0))
    factors["hazard_intensity"] = round(20 * hazard_intensity, 1)
    factors["injured"] = min(10, injured * 2)
    factors["trapped"] = min(10, trapped * 3)
    factors["vulnerable_groups"] = min(5, len(vulnerable_groups or []) * 2)
    factors["spreading"] = 8 if spreading else 0
    factors["structural_damage"] = 7 if structural_damage else 0
    score = round(min(100, sum(factors.values())), 1)
    level = "CRITICAL" if score >= 80 else "HIGH" if score >= 60 else "MODERATE" if score >= 40 else "LOW"
    return {"risk_score": score, "severity": level, "factors": factors,
            "method": "RULE_BASED_PROTOTYPE"}
