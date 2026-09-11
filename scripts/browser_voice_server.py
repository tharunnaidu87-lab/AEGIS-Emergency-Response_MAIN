"""Test-only provider doubles for browser_voice_smoke. Never launch for normal use."""
import os
if not os.environ.get("AEGIS_DB_PATH", "").startswith(".cache/browser-"):
    raise RuntimeError("Voice smoke server requires an isolated browser test database")
os.environ["SARVAM_API_KEY"] = ""
os.environ["NVIDIA_API_KEY"] = ""
import httpx
import main
from speech.sarvam import SarvamSpeechProvider
from nlp.nvidia import NvidiaNLPProvider
from nlp.router import extract

TEXT = "Hostel daggara fire start ayyindi, around twenty students inside unnaru."


class MockSpeech:
    async def transcribe(self, audio, content_type):
        assert len(audio) > 100 and audio[:4] == b'\x1a\x45\xdf\xa3', "Expected real recorded WebM bytes"
        # Exercise the actual HTTP adapter, without network or a real key.
        from unittest.mock import patch
        with patch.dict(os.environ, {"SARVAM_API_KEY": "test"}):
            return await SarvamSpeechProvider(httpx.MockTransport(lambda r: httpx.Response(200,
                json={"transcript": TEXT, "language_code": "te-IN"}))).transcribe(audio, content_type)


async def mock_extract(request):
    if "LOCAL FALLBACK" in request.text:
        return await extract(request)
    if request.source == "SMS":
        return await extract(request)
    import json
    value = dict(incident_type="Fire", location="Hostel", people_affected=20, injured=None, trapped=None,
        vulnerable_groups=[], spreading=None, structural_damage=None, hazard_intensity_estimate=None,
        description=request.text, language="Telugu + English", confidence=None,
        field_confidence={"incident_type": .92, "location": .6}, missing_fields=[], questions=[], warnings=[],
        field_evidence={"incident_type": "fire", "location": "Hostel", "people_affected": "twenty students"})
    provider = NvidiaNLPProvider(httpx.MockTransport(lambda r: httpx.Response(200,
        json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}]})))
    from unittest.mock import patch
    with patch.dict(os.environ, {"NVIDIA_API_KEY": "test"}):
        return await extract(request, provider)


main.SarvamSpeechProvider = MockSpeech
main.extract = mock_extract
app = main.app
