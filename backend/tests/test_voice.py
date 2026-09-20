"""Provider HTTP contracts and provenance using mocks only; never real API credits."""
import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from intake_nlp import ParseRequest
from nlp.provider import NLPUnavailable
from nlp.nvidia import NvidiaNLPProvider
from nlp.router import extract
from speech.sarvam import SarvamSpeechProvider
from speech.provider import SpeechUnavailable
import test_intake
import db
from provider_config import SARVAM_MODEL, NVIDIA_MODEL

TEXT = "Hostel daggara fire start ayyindi, around twenty students inside unnaru."


def facts(**changes):
    return dict(incident_type="Fire", location="Hostel", people_affected=20, injured=None,
        trapped=None, vulnerable_groups=[], spreading=None, structural_damage=None,
        hazard_intensity_estimate=None, description=TEXT, language="Telugu + English",
        confidence=None, field_confidence={"incident_type": .9, "location": .5, "people_affected": .9},
        missing_fields=[], questions=[], warnings=[],
        field_evidence={"incident_type": "fire", "location": "Hostel", "people_affected": "twenty students"}, **changes)


def completion(value):
    return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}]}


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"NVIDIA_API_KEY": "test-nvidia", "SARVAM_API_KEY": "test-sarvam"})
        self.env.start()
        self.addCleanup(self.env.stop)

    async def test_sarvam_audio_auth_auto_language_and_honest_confidence(self):
        def handler(request):
            self.assertEqual(str(request.url), "https://api.sarvam.ai/speech-to-text")
            self.assertEqual(request.headers["api-subscription-key"], "test-sarvam")
            for value in [b'recording.webm', b'unknown', SARVAM_MODEL.encode(), b'audio-sample']:
                self.assertIn(value, request.content)
            if SARVAM_MODEL.startswith("saaras:v3"):
                self.assertIn(b'codemix', request.content)
            else:
                self.assertNotIn(b'codemix', request.content)
            return httpx.Response(200, json={"transcript": TEXT, "language_code": "te-IN", "language_probability": .99})
        result = await SarvamSpeechProvider(httpx.MockTransport(handler)).transcribe(b"audio-sample", "audio/webm;codecs=opus")
        self.assertEqual(result.language_code, "te-IN")
        self.assertEqual(result.transcript, TEXT)
        self.assertIsNone(result.confidence)

    async def test_sarvam_errors_and_invalid_responses_are_redacted(self):
        for status, value in [(403, {"secret": "never-echo"}), (429, {}), (503, {}),
                              (200, {}), (200, {"transcript": " "}), (200, {"transcript": "x" * 5001}), (200, [])]:
            with self.subTest(status=status, value_type=type(value).__name__):
                provider = SarvamSpeechProvider(httpx.MockTransport(lambda r: httpx.Response(status, json=value)))
                with self.assertRaises(SpeechUnavailable) as error:
                    await provider.transcribe(b"audio", "audio/webm")
                self.assertNotIn("never-echo", str(error.exception))

    async def test_sarvam_timeout_and_missing_key(self):
        def timeout(request):
            raise httpx.ReadTimeout("private provider detail")
        with self.assertRaises(SpeechUnavailable):
            await SarvamSpeechProvider(httpx.MockTransport(timeout)).transcribe(b"audio", "audio/webm")
        with patch.dict(os.environ, {"SARVAM_API_KEY": ""}), self.assertRaises(SpeechUnavailable):
            await SarvamSpeechProvider().transcribe(b"audio", "audio/webm")

    async def test_nvidia_strict_extraction_and_clarification(self):
        def handler(request):
            self.assertEqual(request.headers["Authorization"], "Bearer test-nvidia")
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], NVIDIA_MODEL)
            self.assertNotIn("tools", payload)
            self.assertIn(TEXT, payload["messages"][1]["content"])
            return httpx.Response(200, json=completion(facts()))
        provider = NvidiaNLPProvider(httpx.MockTransport(handler))
        result = await extract(ParseRequest(source="CALL", text=TEXT), provider)
        self.assertEqual(result.method, "ADVANCED_NLP")
        self.assertEqual(result.people_affected, 20)
        for key in ["injured", "trapped", "spreading", "structural_damage", "confidence"]:
            self.assertIsNone(getattr(result, key))
        self.assertTrue(any("landmark" in q for q in result.questions))
        self.assertTrue(any("injured" in q for q in result.questions))
        self.assertIn("uncalibrated", result.confidence_basis)
        self.assertIsNone(result.latitude)

    async def test_invalid_json_retries_once_then_local_fallback(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "dispatch fire trucks now"}}]})
        result = await extract(ParseRequest(source="CALL", text="Fire near hostel."), NvidiaNLPProvider(httpx.MockTransport(handler)))
        self.assertEqual(len(calls), 2)
        self.assertEqual(result.method, "LOCAL_RULE_BASED")
        self.assertIsNone(result.people_affected)
        self.assertTrue(any("Using basic emergency analysis" in w for w in result.warnings))

    async def test_schema_rejects_extra_fields_types_and_nonfinite(self):
        for change in [{"dispatch": True}, {"injured": -2}, {"injured": "2"}, {"spreading": "false"},
                       {"confidence": 1.1}, {"confidence": float('nan')}, {"incident_type": "Other"}]:
            with self.subTest(change=change):
                data = {**facts(), **change}
                provider = NvidiaNLPProvider(httpx.MockTransport(lambda r: httpx.Response(200, json=completion(data))))
                with self.assertRaises(NLPUnavailable):
                    await provider.parse(ParseRequest(source="CALL", text=TEXT))

    async def test_retry_recovers_valid_json(self):
        values = iter([{"error": "bad shape"}, completion(facts())])
        provider = NvidiaNLPProvider(httpx.MockTransport(lambda r: httpx.Response(200, json=next(values))))
        self.assertEqual((await provider.parse(ParseRequest(source="CALL", text=TEXT))).people_affected, 20)

    async def test_rate_limit_auth_timeout_fail_closed_without_retry_storm(self):
        for status in [401, 403, 429, 500]:
            calls = []
            def handler(request):
                calls.append(request)
                return httpx.Response(status, json={"private": "never-echo"})
            result = await extract(ParseRequest(source="CALL", text="Fire near hostel."), NvidiaNLPProvider(httpx.MockTransport(handler)))
            self.assertEqual(result.method, "LOCAL_RULE_BASED")
            self.assertEqual(len(calls), 1)
            self.assertNotIn("never-echo", result.model_dump_json())
        def timeout(request):
            raise httpx.ReadTimeout("private detail")
        result = await extract(ParseRequest(source="CALL", text=TEXT), NvidiaNLPProvider(httpx.MockTransport(timeout)))
        self.assertEqual(result.method, "LOCAL_RULE_BASED")

    async def test_unsupported_facts_removed_and_conflicting_counts_questioned(self):
        value = {**facts(), "injured": 45, "structural_damage": True,
                 "field_evidence": {**facts()["field_evidence"], "injured": "45 injured", "structural_damage": "invented damage"}}
        provider = NvidiaNLPProvider(httpx.MockTransport(lambda r: httpx.Response(200, json=completion(value))))
        result = await extract(ParseRequest(source="CALL", text=TEXT), provider)
        self.assertIsNone(result.injured)
        self.assertIsNone(result.structural_damage)
        text = TEXT + " 45 injured."
        result = await extract(ParseRequest(source="CALL", text=text), provider)
        self.assertIsNone(result.people_affected)
        self.assertEqual(result.injured, 45)
        self.assertIn("people_affected", result.missing_fields)


# Reuse fixture lifecycle, not inherited tests (the original 34 run separately).
class VoiceApiTests(unittest.TestCase):
    setUp = test_intake.IntakeApiTests.setUp
    tearDown = test_intake.IntakeApiTests.tearDown

    def test_audio_validation_and_unavailable_provider(self):
        for content, content_type, expected in [(b'audio', 'text/plain', 415), (b'', 'audio/webm', 422),
            (b'a' * (5 * 1024 * 1024 + 1), 'audio/webm', 413), (b'audio', 'audio/webm', 503)]:
            self.assertEqual(self.client.post('/voice/transcribe', content=content, headers={'content-type': content_type}).status_code, expected)

    def test_voice_review_persists_server_provenance_and_corrections(self):
        speech = SarvamSpeechProvider(httpx.MockTransport(lambda r: httpx.Response(200, json={"transcript": TEXT, "language_code": "te-IN"})))
        provider = NvidiaNLPProvider(httpx.MockTransport(lambda r: httpx.Response(200, json=completion(facts()))))
        with patch.dict(os.environ, {"SARVAM_API_KEY": "test", "NVIDIA_API_KEY": "test"}), \
             patch('main.SarvamSpeechProvider', return_value=speech), patch('nlp.router.NvidiaNLPProvider', return_value=provider):
            stt = self.client.post('/voice/transcribe', content=b'audio', headers={'content-type': 'audio/webm'}).json()
            edited = TEXT.replace('twenty', 'twenty-five')
            response = self.client.post('/intake/parse', json={"source": "CALL", "text": edited, "speech_result_id": stt['result_id']})
            self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result['method'], 'ADVANCED_NLP')
        self.assertEqual(self.client.get('/reports').json()['total'], 0)
        payload = dict(source='CALL', raw_content=edited, intake_result_id=result['result_id'], incident_type='Fire',
            location='Hostel main entrance', latitude=13.13, longitude=80.22, people_affected=25, injured=2,
            intake_unknown_fields=['trapped', 'spreading', 'structural_damage'])
        # No provider is invoked by report confirmation, including after an app restart.
        with patch('nlp.nvidia.NvidiaNLPProvider.parse', side_effect=AssertionError('Must not rebill')):
            db.init_db()
            saved = self.client.post('/reports', json=payload)
        self.assertEqual(saved.status_code, 200, saved.text)
        report = saved.json()['report']
        metadata = report['intake']
        self.assertEqual(metadata['original_transcript'], TEXT)
        self.assertEqual(metadata['speech_provider'], 'SARVAM')
        self.assertEqual(metadata['detected_language'], 'te-IN')
        self.assertEqual(metadata['nlp_method'], 'ADVANCED_NLP')
        self.assertEqual(metadata['citizen_corrections']['injured'], {'original': None, 'reviewed': 2})
        self.assertIn('transcript', metadata['citizen_corrections'])
        self.assertIsNone(metadata['reviewed']['trapped'])
        self.assertEqual(self.client.get('/reports/' + report['id']).json()['report']['intake'], metadata)
        self.assertEqual(self.client.get('/assignments').json()['total'], 0)

    def test_expired_or_changed_preview_cannot_create_report(self):
        result = self.client.post('/intake/parse', json={'source': 'CALL', 'text': TEXT}).json()
        payload = dict(source='CALL', raw_content='Changed text', intake_result_id=result['result_id'],
            incident_type='Fire', location='Hostel', latitude=13.13, longitude=80.22, people_affected=0)
        self.assertEqual(self.client.post('/reports', json=payload).status_code, 409)
        payload['raw_content'] = TEXT
        with db.get_connection() as connection:
            connection.execute('UPDATE intake_previews SET created_at=?', (time.time() - 90000,))
        self.assertEqual(self.client.post('/reports', json=payload).status_code, 409)
        self.assertEqual(self.client.get('/reports').json()['total'], 0)

    def test_browser_metadata_and_manual_call_are_additive(self):
        for extra, expected in [({}, 'MANUAL_TEXT'), ({'browser_transcript': TEXT, 'browser_language': 'te-IN'}, 'BROWSER_SPEECH_RECOGNITION')]:
            result = self.client.post('/intake/parse', json={'source': 'CALL', 'text': TEXT, **extra}).json()
            saved = self.client.post('/reports', json=dict(source='CALL', raw_content=TEXT, intake_result_id=result['result_id'],
                incident_type='Fire', location='Hostel', latitude=13.13, longitude=80.22, people_affected=0)).json()['report']
            self.assertEqual(saved['intake']['speech_provider'], expected)
            self.assertIsNone(saved['intake']['detected_language'])
            self.assertEqual(saved['intake']['nlp_method'], 'LOCAL_RULE_BASED')


if __name__ == '__main__':
    unittest.main()
