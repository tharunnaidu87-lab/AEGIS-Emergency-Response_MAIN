"""NLP correctness, unknowns and integration through the existing report pipeline."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from fastapi.testclient import TestClient
import db
from main import app
from intake_nlp import ParseRequest, normalize_numbers, parse_intake
from telecom.provider import InboundMessage, prepare_for_review

FIRE = "There is a fire near the college hostel. The fire is spreading. Around twenty people are inside and two people are injured."
FLOOD = "Flood near Anna Nagar bridge. Water is increasing quickly. Around thirty people are trapped and elderly people are present."


class ParserTests(unittest.TestCase):
    def parse(self, text, **kwargs):
        return parse_intake(ParseRequest(source="SMS", text=text, **kwargs))

    def test_voice_example(self):
        value = self.parse(FIRE)
        self.assertEqual((value.incident_type, value.location, value.people_affected, value.injured),
                         ("Fire", "college hostel", 20, 2))
        self.assertTrue(value.spreading)
        self.assertIsNone(value.structural_damage)

    def test_sms_example(self):
        value = self.parse(FLOOD)
        self.assertEqual((value.incident_type, value.location, value.people_affected, value.trapped),
                         ("Flood", "Anna Nagar bridge", 30, 30))
        self.assertIn("Elderly", value.vulnerable_groups)
        self.assertTrue(value.spreading)

    def test_tamil_flood_fallback_extracts_core_emergency_facts(self):
        text = (
            "ரிவர்பேங்க் கிராமத்தில் பள்ளி அருகே கடுமையான வெள்ளம் ஏற்பட்டுள்ளது. "
            "தண்ணீர் வேகமாக உயர்ந்து அருகிலுள்ள வீடுகளுக்கும் தெருக்களுக்கும் புகுகிறது. "
            "சுமார் 120 பேர் பாதிக்கப்பட்டுள்ளனர், 8 பேர் காயமடைந்துள்ளனர், "
            "15 பேர் வெள்ளம் சூழ்ந்த கட்டிடங்களில் சிக்கியுள்ளனர். "
            "குழந்தைகள், முதியவர்கள், மாற்றுத்திறனாளிகள் மற்றும் மருத்துவ உதவி தேவைப்படும் மக்கள் பாதிக்கப்பட்டவர்களில் உள்ளனர். "
            "பல வீடுகள் கட்டமைப்பு சேதம் அடைந்துள்ளன, மேலும் வெள்ளம் அருகிலுள்ள குடியிருப்பு பகுதிகளுக்கு தொடர்ந்து பரவி வருகிறது."
        )
        value = self.parse(text, latitude=13.13, longitude=80.22, gps_verified=True)
        self.assertEqual(value.incident_type, "Flood")
        self.assertIn("ரிவர்பேங்க்", value.location)
        self.assertEqual((value.people_affected, value.injured, value.trapped), (120, 8, 15))
        for group in ["Children", "Elderly", "Disabled", "Medical dependent"]:
            self.assertIn(group, value.vulnerable_groups)
        self.assertTrue(value.spreading)
        self.assertTrue(value.structural_damage)
        self.assertEqual(value.language, "Tamil")
        self.assertGreaterEqual(value.confidence, .75)

    def test_tamil_unknowns_remain_unknown(self):
        value = self.parse("ரிவர்பேங்க் கிராமத்தில் வெள்ளம் ஏற்பட்டுள்ளது.")
        self.assertEqual(value.incident_type, "Flood")
        self.assertIsNone(value.people_affected)
        self.assertIsNone(value.injured)
        self.assertIsNone(value.trapped)
        self.assertIsNone(value.structural_damage)

    def test_synonyms_and_landmarks(self):
        for kind, terms in {"Fire": ["burning", "smoke", "flames", "explosion"],
            "Flood": ["water rising", "overflow", "water entering", "submerged"],
            "Accident": ["crash", "collision", "vehicle hit"],
            "Landslide": ["mudslide", "rocks falling", "soil collapse"]}.items():
            for term in terms:
                with self.subTest(term=term):
                    self.assertEqual(self.parse(term + " near ABC school").incident_type, kind)
        for term in ["at", "beside", "behind", "opposite", "on"]:
            self.assertEqual(self.parse("Fire " + term + " Anna road.").location, "Anna road")
        self.assertEqual(self.parse("ABC hostel is burning").location, "ABC hostel")

    def test_word_numbers_and_subgroups(self):
        self.assertEqual(normalize_numbers("one hundred and twenty-five people"), "125 people")
        self.assertEqual(normalize_numbers("two thousand and thirty people"), "2030 people")
        result = self.parse("Fire at school. Twenty people and two injured, five trapped.")
        self.assertEqual((result.people_affected, result.injured, result.trapped), (20, 2, 5))
        self.assertIsNone(self.parse("A fire. Two injured.").people_affected)

    def test_unknowns_and_questions(self):
        value = self.parse("There is a fire here.")
        for key in ["location", "people_affected", "injured", "trapped", "spreading", "structural_damage", "latitude", "longitude"]:
            self.assertIsNone(getattr(value, key))
        self.assertIn("Where is the emergency?", value.questions)
        self.assertIn("coordinates", value.missing_fields)
        self.assertIsNone(self.parse("Please help me").incident_type)
        self.assertIsNone(self.parse("Fire and flood near ABC school").incident_type)

    def test_negations_and_no_hallucinated_casualties(self):
        result = self.parse("No fire. Accident near ABC bridge. No one is trapped. No injuries. Not spreading. No structural damage.")
        self.assertEqual(result.incident_type, "Accident")
        self.assertEqual((result.injured, result.trapped), (0, 0))
        self.assertFalse(result.spreading)
        self.assertFalse(result.structural_damage)
        self.assertNotIn("Elderly", self.parse("Fire. No elderly present.").vulnerable_groups)

    def test_vulnerable_and_urgency(self):
        result = self.parse("Fire near ABC school. Children, elderly, disabled, pregnant and medically dependent people. Heavy smoke. Roof collapsed.")
        self.assertEqual(len(result.vulnerable_groups), 5)
        self.assertTrue(result.structural_damage)
        self.assertEqual(result.hazard_intensity, .8)

    def test_counts_are_not_coordinates_phone_numbers_or_ranges(self):
        result = self.parse("Fire at ABC school. Call 9876543210. Latitude 13.13, longitude 80.22.")
        self.assertIsNone(result.people_affected)
        self.assertIsNone(result.latitude)
        for text in ["Fire, -2 people", "Fire, 2.5 people", "Fire, twenty to thirty people", "Fire, 999999999 people"]:
            self.assertIsNone(self.parse(text).people_affected)

    def test_confidence_separate_from_severity_and_gps(self):
        low = self.parse("Fire here")
        full = self.parse(FIRE, latitude=13.13, longitude=80.22, gps_verified=True)
        self.assertGreater(full.confidence, low.confidence)
        self.assertLessEqual(full.confidence, .95)
        self.assertEqual(full.confidence_factors["gps"], 15)
        self.assertNotIn("severity", full.model_dump())
        self.assertNotIn("assignments", full.model_dump())

    def test_provider_boundary_does_not_invent_gps(self):
        result = prepare_for_review(InboundMessage(provider_message_id="test-event", source="CALL", sender="verified-by-future-provider", text=FIRE))
        self.assertEqual(result.source, "CALL")
        self.assertIsNone(result.latitude)


class IntakeApiTests(unittest.TestCase):
    def setUp(self):
        self.provider_env = patch.dict(os.environ, {"SARVAM_API_KEY": "", "NVIDIA_API_KEY": ""})
        self.provider_env.start()
        self.addCleanup(self.provider_env.stop)
        directory = ROOT / ".cache" / "tests"
        directory.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=directory)
        self.patch = patch.object(db, "DB_PATH", Path(self.temp.name) / "intake.sqlite")
        self.patch.start()
        self.auth_env = patch.dict(os.environ, {"AEGIS_COMMAND_USERNAME": "test-command", "AEGIS_COMMAND_PASSWORD": "test-password", "AEGIS_COMMAND_AUTH_SECRET": "test-secret-only"})
        self.auth_env.start()
        self.addCleanup(self.auth_env.stop)
        self.client = TestClient(app)
        self.client.__enter__()
        from command_auth import create_command_token
        token, _ = create_command_token('test-command')
        self.client.headers['Authorization'] = 'Bearer ' + token

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.patch.stop()
        self.temp.cleanup()

    def test_parse_endpoint_is_side_effect_free(self):
        result = self.client.post("/intake/parse", json={"source": "CALL", "text": FIRE})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["injured"], 2)
        self.assertEqual(self.client.get("/reports").json()["total"], 0)
        self.assertEqual(self.client.get("/assignments").json()["total"], 0)
        self.assertEqual(self.client.get("/intake/capabilities").json()["telecom"], "PROVIDER_READY_NOT_CONFIGURED")

    def test_bad_parse_requests(self):
        for changes in [dict(text=" "), dict(text="x" * 5001), dict(source="APP"), dict(latitude=91, longitude=80),
                        dict(latitude=13), dict(gps_verified=True), dict(latitude="NaN", longitude=80), dict(extra="no")]:
            with self.subTest(changes=changes):
                response = self.client.post("/intake/parse", json={"source": "SMS", "text": FIRE, **changes})
                self.assertEqual(response.status_code, 422)

    def test_channel_review_persistence_fusion_and_dispatch(self):
        base = dict(incident_type="Fire", location="college hostel", people_affected=20, injured=2, trapped=0,
                    spreading=True, hazard_intensity=.8, latitude=13.13, longitude=80.22, description=FIRE,
                    gps_verified=True, intake_unknown_fields=["trapped", "structural_damage"])
        reports = []
        for source in ["APP", "SMS", "CALL"]:
            payload = {**base, "source": source, "raw_content": FIRE if source != "APP" else "", "injured": 3}
            response = self.client.post("/reports", json=payload)
            self.assertEqual(response.status_code, 200, response.text)
            reports.append(response.json()["report"])
        self.assertEqual(len({r["fusion_id"] for r in reports}), 1)
        self.assertIsNone(reports[0]["intake"])
        for report in reports[1:]:
            self.assertEqual(report["raw_content"], FIRE)
            metadata = report["intake"]
            self.assertEqual(metadata["extraction"]["injured"], 2)
            self.assertEqual(metadata["reviewed"]["injured"], 3)
            self.assertIsNone(metadata["reviewed"]["trapped"])
            self.assertIn("injured", metadata["corrected_fields"])
            self.assertEqual(self.client.get('/reports/' + report['id']).json()['report']['intake'], metadata)
        self.assertEqual(self.client.get("/assignments").json()["total"], 0)
        result = self.client.post('/reports/' + reports[0]['id'] + '/dispatch')
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.json()["assignments"])
        again = self.client.post('/reports/' + reports[2]['id'] + '/dispatch').json()
        self.assertTrue(again["already_dispatched"])
        self.assertEqual(len(again["assignments"]), len(result.json()["assignments"]))
        events = self.client.get('/audit-events').json()['events']
        self.assertEqual(sum(e['event_type'] == 'INTAKE_REVIEWED' for e in events), 2)

    def test_intake_migration_preserves_existing_report(self):
        # Simulate the exact pre-upgrade schema by removing the new nullable column.
        payload = dict(incident_type="Accident", location="ABC road", latitude=13.13, longitude=80.22, people_affected=2)
        report = self.client.post('/reports', json=payload).json()['report']
        with db.get_connection() as connection:
            connection.execute('ALTER TABLE reports DROP COLUMN intake_json')
        db.init_db()
        preserved = self.client.get('/reports/' + report['id']).json()['report']
        self.assertEqual(preserved, report)


if __name__ == '__main__':
    unittest.main()
