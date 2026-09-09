"""Evidence quality, not a probability. Repeated identical content adds no evidence."""


def calculate_confidence(reports):
    unique = {}
    for report in reports:
        # Contact is not proof of identity; this only avoids obvious repeated submissions.
        key = (report.get("phone", ""), report.get("description", "").strip().lower(),
               round(report.get("latitude", 0), 3), round(report.get("longitude", 0), 3))
        unique.setdefault(key, report)
    evidence = list(unique.values())
    factors = {"base_report": 35 if evidence else 0,
               "distinct_reports": min(24, max(0, len(evidence) - 1) * 8),
               "source_diversity": min(12, max(0, len({r.get('source', 'APP') for r in evidence}) - 1) * 6),
               "browser_gps": 14 if any(r.get("gps_verified") for r in evidence) else 0,
               "description": 8 if any(len(r.get("description", "")) >= 20 for r in evidence) else 0}
    return {"score": min(95, sum(factors.values())), "report_count": len(reports),
            "distinct_evidence_count": len(evidence), "factors": factors,
            "method": "RULE_BASED_EVIDENCE_QUALITY", "identity_verified": False}
