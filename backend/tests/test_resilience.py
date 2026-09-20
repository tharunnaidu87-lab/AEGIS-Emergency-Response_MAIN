"""Critical security/delivery invariants with separate citizen, authority and responder clients."""
import base64
import concurrent.futures
import io
import json
import os
import time
import unittest
from unittest.mock import patch
from PIL import Image
from fastapi.testclient import TestClient
import test_intake
from main import app
from test_aegis import PAYLOAD
import db
from command_auth import create_command_token


class ResilienceTests(unittest.TestCase):
    setUp = test_intake.IntakeApiTests.setUp
    tearDown = test_intake.IntakeApiTests.tearDown

    def citizen(self):
        return TestClient(app)

    def responder(self, unit):
        self.accounts = patch.dict(os.environ, {'AEGIS_RESPONDER_ACCOUNTS': json.dumps({unit: 'unit-password'})})
        self.accounts.start(); self.addCleanup(self.accounts.stop)
        client = self.citizen()
        login = client.post('/auth/responder/login', json={'username': unit, 'password': 'unit-password'})
        self.assertEqual(login.status_code, 200, login.text)
        client.headers['Authorization'] = 'Bearer ' + login.json()['token']
        return client

    def test_citizen_cannot_read_or_dispatch_staff_data(self):
        citizen = self.citizen()
        receipt = citizen.post('/reports', json=PAYLOAD).json()
        rid = receipt['report']['id']
        for route in ['/reports', '/assignments', '/resources', '/audit-events', '/distress', '/reports/' + rid]:
            self.assertEqual(citizen.get(route).status_code, 401, route)
        for route in ['/demo/reset', '/reports/' + rid + '/dispatch']:
            self.assertEqual(citizen.post(route).status_code, 401)
        self.assertEqual(citizen.get('/reports/' + rid, headers={'X-Report-Token': receipt['tracking_token']}).status_code, 200)
        other = citizen.post('/reports', json={**PAYLOAD, 'longitude': 81}).json()['report']['id']
        self.assertEqual(citizen.get('/reports/' + other, headers={'X-Report-Token': receipt['tracking_token']}).status_code, 401)
        self.assertNotIn('tracking_token', self.client.get('/reports').text)

    def test_responder_owns_only_assigned_missions(self):
        report = self.client.post('/reports', json=PAYLOAD).json()['report']
        assignments = self.client.post('/reports/' + report['id'] + '/dispatch').json()['assignments']
        own, other = assignments[:2]
        unassigned_report = self.client.post(
            '/reports',
            json={**PAYLOAD, 'location': 'Unassigned incident', 'latitude': 14.5},
        ).json()['report']
        responder = self.responder(own['resource_id'])
        self.assertEqual(responder.get('/assignments').status_code, 403)
        self.assertEqual(responder.get('/assignments', params={'resource_id': other['resource_id']}).status_code, 403)
        self.assertEqual(responder.get('/assignments', params={'resource_id': own['resource_id']}).status_code, 200)
        self.assertEqual(responder.get('/reports/' + report['id']).status_code, 200)
        self.assertEqual(responder.get('/reports/' + unassigned_report['id']).status_code, 401)
        self.assertEqual(responder.get('/resources').status_code, 401)
        self.assertEqual(responder.patch('/assignments/' + other['id'] + '/status', json={'status': 'EN_ROUTE'}).status_code, 403)
        self.assertEqual(responder.patch('/assignments/' + own['id'] + '/status', json={'status': 'ACCEPTED'}).status_code, 200)
        self.assertEqual(responder.post('/assignments/' + own['id'] + '/reassign').status_code, 401)
        self.assertEqual(responder.post('/reports', json=PAYLOAD).status_code, 403)
        self.assertEqual(responder.get('/auth/command/session').status_code, 401)
        self.assertEqual(self.client.get('/auth/responder/session').status_code, 401)

    def test_missing_expired_tampered_and_unicode_sessions(self):
        citizen = self.citizen()
        self.assertEqual(citizen.get('/auth/command/session').status_code, 401)
        token, _ = create_command_token('test-command')
        for bad in [token + 'x', 'abc.def', 'bad', 'a.b.c']:
            self.assertEqual(citizen.get('/reports', headers={'Authorization': 'Bearer ' + bad}).status_code, 401)
        with patch('command_auth.time.time', return_value=time.time() + 50000):
            self.assertEqual(citizen.get('/reports', headers={'Authorization': 'Bearer ' + token}).status_code, 401)
        self.assertEqual(citizen.post('/auth/command/login', json={'username': 'తెలుగు', 'password': 'సంకేతం'}).status_code, 401)

    def test_retry_receipt_atomic_idempotency_concurrent_and_restarted(self):
        payload = {**PAYLOAD, 'client_request_id': 'same-request-00000001'}
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            responses = list(pool.map(lambda _: self.citizen().post('/reports', json=payload), range(5)))
        self.assertTrue(all(r.status_code == 200 for r in responses), [r.text for r in responses])
        self.assertEqual(len({r.json()['report']['id'] for r in responses}), 1)
        self.assertEqual(len({r.json()['tracking_token'] for r in responses}), 1)
        db.init_db()
        repeated = self.citizen().post('/reports', json=payload).json()
        self.assertEqual(repeated, responses[0].json())
        self.assertEqual(self.citizen().post('/reports', json={**payload, 'description': 'Different incident'}).status_code, 409)
        self.assertEqual(self.client.get('/reports').json()['total'], 1)

    def test_photos_decode_strip_metadata_and_require_receipt(self):
        image = Image.new('RGB', (40, 30), 'red'); output = io.BytesIO()
        exif = Image.Exif(); exif[270] = 'private-metadata'
        image.save(output, 'JPEG', exif=exif)
        receipt = self.citizen().post('/reports', json={**PAYLOAD, 'photos': [base64.b64encode(output.getvalue()).decode()]}).json()
        rid = receipt['report']['id']; mid = receipt['report']['photo_ids'][0]
        self.assertEqual(self.citizen().get('/media/' + mid).status_code, 401)
        photo = self.citizen().get('/media/' + mid, headers={'X-Report-Token': receipt['tracking_token']})
        self.assertEqual(photo.status_code, 200)
        self.assertNotIn(b'private-metadata', photo.content)
        self.assertEqual(photo.headers['x-content-type-options'], 'nosniff')
        self.assertEqual(Image.open(io.BytesIO(photo.content)).format, 'JPEG')
        self.assertEqual(self.client.get('/reports/' + rid).json()['report']['photo_ids'], [mid])

    def test_malicious_media_rolls_back_whole_report(self):
        for photo in ['!!!!', base64.b64encode(b'<svg onload="alert(1)">').decode(), base64.b64encode(b'MZ executable').decode()]:
            response = self.citizen().post('/reports', json={**PAYLOAD, 'photos': [photo]})
            self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.get('/reports').json()['total'], 0)
        self.assertEqual(self.citizen().post('/reports', content=b'x' * (6 * 1024 * 1024)).status_code, 413)

    def test_release_input_boundaries_do_not_persist_invalid_data(self):
        tiny = io.BytesIO()
        Image.new('RGB', (2, 2), 'blue').save(tiny, 'PNG')
        encoded = base64.b64encode(tiny.getvalue()).decode()
        self.assertEqual(
            self.citizen().post('/reports', json={**PAYLOAD, 'photos': [encoded] * 3}).status_code,
            422,
        )
        invalid_signals = [
            {'client_request_id': 'invalid-coord-0001', 'captured_at': '2026-09-16', 'latitude': 13.1},
            {'client_request_id': 'invalid-extra-0001', 'captured_at': '2026-09-16', 'unexpected': True},
            {'client_request_id': 'invalid-voice-0001', 'captured_at': '2026-09-16', 'kind': 'VOICE'},
        ]
        for payload in invalid_signals:
            with self.subTest(payload=payload['client_request_id']):
                self.assertEqual(self.citizen().post('/distress', json=payload).status_code, 422)
        self.assertEqual(self.client.get('/reports').json()['total'], 0)
        self.assertEqual(self.client.get('/distress').json(), [])

    def test_known_sos_high_priority_police_only_no_duplicate_mission(self):
        payload = {'client_request_id': 'sos-known-00000001', 'kind': 'SOS', 'captured_at': '2026-09-16T10:00:00Z', 'latitude': 13.13, 'longitude': 80.22, 'accuracy': 15}
        citizen = self.citizen()
        receipt = citizen.post('/distress', json=payload).json()
        self.assertEqual(receipt['status'], 'DEMO_MISSION_ASSIGNED')
        assignments = self.client.get('/assignments').json()['assignments']
        self.assertEqual(len(assignments), 1)
        self.assertEqual(assignments[0]['resource_type'], 'POLICE')
        report = self.client.get('/reports/' + receipt['report_id']).json()['report']
        self.assertEqual(report['analysis']['result']['severity_analysis']['severity'], 'HIGH')
        self.assertEqual(report['analysis']['result']['hazard_analysis']['current_radius_km'], 0)
        self.assertEqual(citizen.post('/distress', json=payload).json()['report_id'], receipt['report_id'])
        self.assertEqual(self.client.get('/assignments').json()['total'], 1)
        self.assertEqual(citizen.get('/distress/' + receipt['id']).status_code, 401)
        self.assertEqual(citizen.get('/distress/' + receipt['id'], headers={'X-Report-Token': receipt['tracking_token']}).status_code, 200)

    def test_missing_sos_location_visible_without_fake_coordinates(self):
        receipt = self.citizen().post('/distress', json={'client_request_id': 'sos-pending-000001', 'captured_at': '2026-09-16'}).json()
        self.assertEqual(receipt['status'], 'LOCATION_NEEDED')
        self.assertIsNone(receipt['context']['latitude'])
        self.assertEqual(self.client.get('/assignments').json()['total'], 0)
        self.assertEqual(len(self.client.get('/distress').json()), 1)
        response = self.client.patch('/distress/' + receipt['id'], json={'latitude': 13.13, 'longitude': 80.22})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['report_id'])
        escalation = self.client.patch('/distress/' + receipt['id'], json={'resource_type': 'AMBULANCE'})
        self.assertEqual(escalation.status_code, 200, escalation.text)
        self.assertEqual({a['resource_type'] for a in self.client.get('/assignments').json()['assignments']}, {'POLICE', 'AMBULANCE'})

    def test_deferred_voice_keeps_original_audio_without_dispatch(self):
        raw = b'\x1aE\xdf\xa3test-fixture-not-real-speech'
        receipt = self.citizen().post('/distress', json={'client_request_id': 'voice-deferred-0001', 'kind': 'VOICE', 'captured_at': '2026-09-16', 'audio': base64.b64encode(raw).decode()}).json()
        self.assertTrue(receipt['has_audio'])
        self.assertNotIn('audio', receipt['context'])
        db.init_db()
        self.assertEqual(self.client.get('/distress/' + receipt['id'] + '/audio').content, raw)
        self.assertEqual(self.client.get('/assignments').json()['total'], 0)
        self.assertEqual(self.client.get('/reports').json()['total'], 0)


    def test_nearby_distinct_landmarks_do_not_fuse(self):
        first = self.client.post('/reports', json={**PAYLOAD, 'incident_type': 'Fire', 'location': 'North Hostel'}).json()['report']
        second = self.client.post('/reports', json={**PAYLOAD, 'incident_type': 'Fire', 'location': 'South Warehouse', 'latitude': 13.1305}).json()['report']
        self.assertNotEqual(first['fusion_id'], second['fusion_id'])
        self.assertEqual(self.client.get('/assignments').json()['total'], 0)

    def test_review_retained_voice_then_normal_approval(self):
        receipt = self.citizen().post('/distress', json={'client_request_id': 'voice-review-000001', 'kind': 'VOICE', 'captured_at': '2026-09-16', 'text': 'Fire at the school, two people inside.'}).json()
        result = self.client.patch('/distress/' + receipt['id'], json={'latitude': 13.14, 'longitude': 80.22, 'incident_type': 'Fire', 'people_affected': 2})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['status'], 'REVIEWED_AWAITING_APPROVAL')
        self.assertEqual(self.client.get('/assignments').json()['total'], 0)
        rid = result.json()['report_id']
        self.assertEqual(self.client.post('/reports/' + rid + '/dispatch').status_code, 200)

    def test_sos_outside_catalog_does_not_fake_a_response(self):
        receipt = self.citizen().post('/distress', json={'client_request_id': 'sos-outside-000001', 'captured_at': '2026-09-16', 'latitude': 0, 'longitude': 0}).json()
        self.assertEqual(receipt['status'], 'AWAITING_AVAILABLE_DEMO_UNIT')
        self.assertEqual(self.client.get('/assignments').json()['total'], 0)

    def test_provider_health_distinguishes_configuration_from_probe(self):
        import provider_health
        with patch.dict(provider_health._state, {}, clear=True):
            self.assertEqual(self.citizen().get('/intake/capabilities').json()['provider_health']['speech']['status'], 'NOT_PROBED')
            for _ in range(3): provider_health.record('speech', False, 'TimeoutError')
            self.assertTrue(provider_health.paused('speech'))
            provider_health.record('speech', True)
            self.assertFalse(provider_health.paused('speech'))
