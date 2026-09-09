"""Critical invariants and real FastAPI integration, isolated from saved demo data."""
import concurrent.futures
import json
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
warnings.filterwarnings("ignore", message="Using .httpx. with .starlette.testclient.")
from fastapi.testclient import TestClient
import db
from main import app
from engines.capacity_engine import calculate_centre_capacity
from engines.resource_engine import allocate_resources, haversine_distance
from engines.severity_engine import calculate_severity

PAYLOAD = dict(incident_type="Flood", location="Riverbank Village", latitude=13.13,
               longitude=80.22, people_affected=18, hazard_intensity=.8,
               description="Flood water entering homes and blocking streets.",
               injured=3, trapped=4, spreading=True, vulnerable_groups=["Children"])


class AegisTests(unittest.TestCase):
    def setUp(self):
        directory = ROOT / ".cache" / "tests"
        directory.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=directory)
        self.path = Path(self.temp.name) / "test.sqlite"
        self.patch = patch.object(db, "DB_PATH", self.path)
        self.patch.start()
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.patch.stop()
        self.temp.cleanup()

    def report(self, **changes):
        response = self.client.post("/reports", json={**PAYLOAD, **changes})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["report"]

    def analyse(self, **changes):
        response = self.client.post("/aegis-analyse", json={**PAYLOAD, **changes})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["result"]

    def dispatch(self, report):
        response = self.client.post(f"/reports/{report['id']}/dispatch")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["assignments"]

    def status(self, assignment, status):
        return self.client.patch(f"/assignments/{assignment['id']}/status", json={"status": status})

    def test_health_empty_and_legacy_endpoints(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/reports").json()["total"], 0)
        for path, payload in [("/incident", PAYLOAD), ("/hazard-analysis", PAYLOAD),
                              ("/relocation-plan", dict(latitude=13.13, longitude=80.22, people_to_relocate=20))]:
            self.assertEqual(self.client.post(path, json=payload).status_code, 200, path)
        self.assertEqual(self.client.get("/relocation-centres").status_code, 200)

    def test_legacy_analysis_upgrade_preserves_operations(self):
        import operations
        report = self.report()
        assignments = self.dispatch(report)
        legacy = dict(report["analysis"])
        legacy["result"] = {k: v for k, v in legacy["result"].items()
                            if k not in {"pipeline", "prediction", "prepositioning"}}
        with db.get_connection() as connection:
            connection.execute("UPDATE reports SET analysis_json=? WHERE id=?",
                               (json.dumps(legacy), report["id"]))
        self.assertEqual(operations.upgrade_legacy_analyses(), 1)
        updated = db.get_report(report["id"])
        self.assertEqual(updated["status"], "DISPATCHED")
        self.assertEqual(updated["people_affected"], report["people_affected"])
        self.assertTrue(updated["analysis"]["result"]["prediction"])
        self.assertEqual(db.list_assignments(), assignments)
        events = db.list_audit_events(report_id=report["id"])
        upgrades = [event for event in events if event["event_type"] == "ANALYSIS_UPGRADED"]
        self.assertEqual(len(upgrades), 1)
        self.assertEqual(upgrades[0]["metadata"]["previous_analysis"], legacy)
        self.assertEqual(operations.upgrade_legacy_analyses(), 0)

    def test_invalid_requests(self):
        for change in [dict(latitude=91), dict(longitude=-181), dict(latitude="NaN"),
                       dict(hazard_intensity=-.1), dict(hazard_intensity=1.1),
                       dict(people_affected=-1), dict(people_affected=1.4), dict(injured=19),
                       dict(trapped=19), dict(incident_type="Unknown"), dict(location=" "),
                       dict(description="a" * 5001)]:
            with self.subTest(change=change):
                self.assertEqual(self.client.post("/reports", json={**PAYLOAD, **change}).status_code, 422)
        self.assertEqual(self.client.post("/aegis-analyse", json={}).status_code, 422)
        self.assertEqual(self.client.get("/reports?limit=-1").status_code, 422)

    def test_missing_report_and_reset_guard(self):
        self.assertEqual(self.client.get("/reports/missing").status_code, 404)
        self.assertEqual(self.client.post("/reports/missing/dispatch").status_code, 404)
        self.assertEqual(self.client.post("/demo/reset").status_code, 403)

    def test_severity_uses_hazard_victims_and_factors(self):
        low = calculate_severity("Flood", 18, .2)
        high = calculate_severity("Flood", 18, .9, injured=3, trapped=4, spreading=True)
        self.assertGreater(high["risk_score"], low["risk_score"])
        self.assertEqual(high["risk_score"], min(100, sum(high["factors"].values())))

    def test_zero_hazard_and_distant_incident_no_local_evacuation(self):
        for changes in [dict(hazard_intensity=0), dict(latitude=0, longitude=0)]:
            with self.subTest(changes=changes):
                result = self.analyse(**changes)
                self.assertEqual(result["people_requiring_relocation"], 0)
                self.assertTrue(all(h["estimated_affected_population"] == 0 for h in result["hazard_analysis"]["habitations"]))
        self.assertEqual(self.analyse(latitude=0, longitude=0)["resource_plan"]["selected_resources"], [])

    def test_capacity_minimum_and_nonnegative(self):
        c = dict(id="S", name="School", latitude=0, longitude=0, risk_status="SAFE",
                 space_capacity=100, water_capacity=80, food_capacity=90, sanitation_capacity=70,
                 medical_capacity=85, current_occupancy=90)
        result = calculate_centre_capacity(c)
        self.assertEqual(result["safe_carrying_capacity"], 70)
        self.assertEqual(result["available_capacity"], 0)
        self.assertEqual(result["limiting_factor"], "sanitation")

    def test_relocation_conserves_population_and_excludes_predicted_footprint(self):
        result = self.analyse()
        plan = result["relocation_plan"]
        self.assertGreater(plan["total_allocated"], 0)
        self.assertEqual(plan["total_allocated"] + plan["unallocated_people"], result["people_requiring_relocation"])
        self.assertEqual(sum(a["people_allocated"] for a in plan["assignments"]), plan["total_allocated"])
        for a in plan["assignments"]:
            self.assertLessEqual(a["people_allocated"], a["available_before_allocation"])
            self.assertEqual(a["remaining_capacity_after"], a["available_before_allocation"] - a["people_allocated"])
            self.assertGreater(a["distance_km"], result["prediction"]["future_radius_km"])

    def test_hospital_capability_capacity_safety(self):
        for kind in ["Flood", "Fire", "Accident", "Landslide"]:
            result = self.analyse(incident_type=kind)
            h = result["hospital_plan"]["selected_hospital"]
            self.assertIsNotNone(h, kind)
            self.assertGreater(h["distance_km"], result["prediction"]["future_radius_km"])
            if kind == "Fire":
                self.assertTrue(h["burn_unit"])
        self.assertIsNone(self.analyse(scenario={"hospital_capacity_factor": 0})["hospital_plan"]["selected_hospital"])

    def test_fusion_maximum_observation_and_shared_status(self):
        first = self.report()
        second = self.report(people_affected=25, description="Second observation: water continues to enter homes.")
        self.assertEqual(first["fusion_id"], second["fusion_id"])
        updated = self.client.get("/reports/" + first["id"]).json()["report"]
        self.assertEqual(updated["people_affected"], 18)  # Original observation retained.
        self.assertEqual(updated["analysis"]["result"]["incident"]["reported_people_affected"], 25)
        self.assertEqual(updated["analysis"]["result"]["fusion"]["report_count"], 2)
        assignments = self.dispatch(second)
        self.assertTrue(all(a["report_id"] == first["id"] for a in assignments))
        self.assertEqual(len(self.dispatch(first)), len(assignments))
        self.assertEqual(self.client.get("/reports/" + second["id"]).json()["report"]["status"], "DISPATCHED")
        self.assertEqual(self.client.get("/assignments?report_id=" + second["id"]).json()["total"], len(assignments))

    def test_repeated_content_not_independent_evidence(self):
        first = self.report()
        second = self.report()
        self.assertEqual(first["analysis"]["result"]["confidence_analysis"]["score"],
                         second["analysis"]["result"]["confidence_analysis"]["score"])
        self.assertEqual(second["analysis"]["result"]["confidence_analysis"]["distinct_evidence_count"], 1)

    def test_separate_incidents_do_not_share_units(self):
        first = self.report()
        second = self.report(latitude=13.23, longitude=80.26, location="Separate flood")
        self.assertNotEqual(first["fusion_id"], second["fusion_id"])
        units_a = {a["resource_id"] for a in self.dispatch(first)}
        units_b = {a["resource_id"] for a in self.dispatch(second)}
        self.assertFalse(units_a & units_b)

    def test_concurrent_dispatch_is_atomic(self):
        first = self.report()
        second = self.report(latitude=13.23, longitude=80.26, location="Separate flood")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self.dispatch, [first, second]))
        self.assertFalse({a["resource_id"] for a in results[0]} & {a["resource_id"] for a in results[1]})

    def test_status_transitions_and_idempotent_departure(self):
        assignments = self.dispatch(self.report())
        a, b = assignments[:2]
        self.assertEqual(self.status(a, "RESOLVED").status_code, 409)
        enroute = self.status(a, "EN_ROUTE").json()["assignment"]
        repeat = self.status(a, "EN_ROUTE").json()["assignment"]
        self.assertEqual(enroute["updated_at"], repeat["updated_at"])
        self.assertEqual(enroute["departed_at"], repeat["departed_at"])
        self.assertEqual(self.status(a, "ON_SCENE").status_code, 200)
        self.assertEqual(self.status(b, "EN_ROUTE").status_code, 200)
        report = self.client.get("/reports/" + a["report_id"]).json()["report"]
        self.assertEqual(report["status"], "ON_SCENE")
        self.assertEqual(self.status(a, "ACCEPTED").status_code, 409)

    def test_reassignment_and_audit(self):
        assignments = self.dispatch(self.report())
        a = next(a for a in assignments if a["resource_type"] == "POLICE")
        self.assertEqual(self.status(a, "ISSUE").status_code, 200)
        response = self.client.post("/assignments/" + a["id"] + "/reassign", json={"reason": "Vehicle failure"})
        self.assertEqual(response.status_code, 200, response.text)
        replacement = response.json()["replacement_assignment"]
        self.assertNotEqual(replacement["resource_id"], a["resource_id"])
        self.assertEqual(replacement["replaces_assignment_id"], a["id"])
        again = self.client.post("/assignments/" + a["id"] + "/reassign", json={})
        self.assertTrue(again.json()["already_reassigned"])
        self.assertEqual(self.status(a, "EN_ROUTE").status_code, 409)
        self.assertTrue(any(e["event_type"] == "ASSIGNMENT_REASSIGNED" for e in self.client.get("/audit-events").json()["events"]))

    def test_what_if_recalculates_and_does_not_mutate(self):
        report = self.report()
        assignments = self.dispatch(report)
        before = self.client.get("/reports/" + report["id"]).json()["report"]
        result = self.analyse(report_id=report["id"], hazard_intensity=.95,
                              scenario={"shelter_capacity_factor": 0, "hospital_capacity_factor": 0,
                                        "unavailable_resource_ids": [assignments[0]["resource_id"]], "road_blocked": True})
        self.assertGreater(result["severity_analysis"]["risk_score"], before["analysis"]["result"]["severity_analysis"]["risk_score"])
        self.assertEqual(result["relocation_plan"]["total_allocated"], 0)
        self.assertIsNone(result["hospital_plan"]["selected_hospital"])
        self.assertNotIn(assignments[0]["resource_id"], {r["id"] for r in result["resource_plan"]["selected_resources"]})
        self.assertEqual(before, self.client.get("/reports/" + report["id"]).json()["report"])

    def test_prediction_drives_safe_spare_staging(self):
        result = self.analyse()
        prediction = result["prediction"]
        self.assertGreater(prediction["future_radius_km"], prediction["current_radius_km"])
        self.assertGreater(prediction["additional_population_at_risk"], 0)
        self.assertTrue(result["prepositioning"])
        assigned = {r["id"] for r in result["resource_plan"]["selected_resources"]}
        for stage in result["prepositioning"]:
            self.assertNotIn(stage["resource_id"], assigned)
            self.assertGreater(haversine_distance(PAYLOAD["latitude"], PAYLOAD["longitude"],
                               stage["latitude"], stage["longitude"]), prediction["future_radius_km"])

    def test_persistence_reconnect(self):
        report = self.report()
        db.init_db()  # Reinitializing does not seed or erase incidents.
        with TestClient(app) as second:
            self.assertEqual(second.get("/reports/" + report["id"]).json()["report"]["id"], report["id"])

    def test_zero_population_and_fully_closed_shelters(self):
        result = self.analyse(people_affected=0, injured=0, trapped=0, hazard_intensity=0)
        self.assertEqual(result["relocation_plan"]["unallocated_people"], 0)
        self.assertEqual(result["relocation_plan"]["coverage_percent"], 100)
        closed = self.analyse(scenario={"shelter_capacity_factor": 0})["relocation_plan"]
        self.assertEqual(closed["total_allocated"], 0)
        self.assertEqual(closed["unallocated_people"], closed["people_requiring_relocation"])

    def test_resource_requirements_and_unavailable_unit(self):
        baseline = allocate_resources("Flood", 18, 13.13, 80.22)
        unit = baseline["selected_resources"][0]
        blocked = allocate_resources("Flood", 18, 13.13, 80.22, unavailable_ids={unit["id"]})
        self.assertNotIn(unit["id"], {r["id"] for r in blocked["selected_resources"]})
        for shortage in blocked["shortages"]:
            self.assertEqual(shortage["required"] - shortage["available"], shortage["shortage"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
