"""One synthetic, bounded live NLP diagnostic. Never prints keys, transcripts or provider bodies."""
import asyncio
import json
import sys
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from provider_config import api_key, NVIDIA_MODEL
from intake_nlp import ParseRequest
from nlp.router import extract
from provider_health import snapshot


async def main():
    started = time.monotonic()
    result = {'configured': bool(api_key('NVIDIA_API_KEY')), 'model': NVIDIA_MODEL, 'input': 'Synthetic demo text only'}
    if result['configured']:
        extracted = await extract(ParseRequest(source='CALL', text='Hostel daggara fire start ayyindi, around twenty students inside unnaru.'))
        result.update(method=extracted.method, incident_type=extracted.incident_type,
                      people_affected=extracted.people_affected, duration_seconds=round(time.monotonic()-started, 2), health=snapshot())
    directory = ROOT / '.cache' / 'verification'
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'live-provider-probe.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))

if __name__ == '__main__':
    asyncio.run(main())
