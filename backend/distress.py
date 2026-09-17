"""SOS and deferred voice receipts. All missions use the local demo catalogue."""
import asyncio
import base64
import hmac
import json
import secrets
import time
from typing import Literal
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
import db
import intake_delivery as delivery
import operations
from provider_config import api_key
from speech.sarvam import SarvamSpeechProvider
from speech.provider import SpeechUnavailable

router = APIRouter()


class DistressRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    client_request_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{16,64}$')
    kind: Literal['SOS', 'VOICE'] = 'SOS'
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    accuracy: float | None = Field(default=None, ge=0, le=1000000)
    captured_at: str = Field(max_length=60)
    location: str = Field(default='', max_length=200)
    text: str = Field(default='', max_length=5000)
    audio: str | None = Field(default=None, max_length=7000000)
    online: bool = True

    @model_validator(mode='after')
    def pairs(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError('Provide both coordinates or neither')
        if self.kind == 'SOS' and self.audio:
            raise ValueError('SOS does not require audio')
        if self.kind == 'VOICE' and not self.audio and not self.text.strip():
            raise ValueError('Record audio or provide a message')
        if self.audio:
            try:
                raw = base64.b64decode(self.audio, validate=True)
                if len(raw) > 5 * 1024 * 1024 or not raw.startswith(b'\x1aE\xdf\xa3'):
                    raise ValueError('audio')
            except Exception:
                raise ValueError('Choose a short WebM recording') from None
        return self


def view(row, include_token=False):
    item = dict(row)
    payload = json.loads(item.pop('payload'))
    item.pop('request_hash')
    if not include_token:
        item.pop('tracking_token')
    item['context'] = {k: v for k, v in payload.items() if k != 'audio'}
    item['has_audio'] = bool(payload.get('audio'))
    item['priority'] = 'HIGH' if item['kind'] == 'SOS' else 'AWAITING_REVIEW'
    item['simulation'] = True
    return item


def get_row(event_id):
    with db.get_connection() as conn:
        return conn.execute('SELECT * FROM distress WHERE id=?', (event_id,)).fetchone()


def materialize(event_id):
    row = get_row(event_id)
    if row['report_id'] and row['status'] not in {'RECEIVED', 'AWAITING_AVAILABLE_DEMO_UNIT'}:
        return
    payload = json.loads(row['payload'])
    if payload['latitude'] is None:
        return
    if row['kind'] != 'SOS':
        return  # Deferred audio is evidence for human review, never an automatic classified dispatch.
    report = operations.submit(dict(client_request_id='distress_' + event_id, incident_type='SOS',
        source='APP', location=payload['location'] or 'SOS location (user device)', latitude=payload['latitude'],
        longitude=payload['longitude'], people_affected=0, hazard_intensity=0,
        description='Unverified distress signal. Hazard and people affected are unknown. DEMO police-first response.',
        gps_verified=False, vulnerable_groups=[]))
    with db.get_connection() as conn:
        conn.execute('UPDATE distress SET report_id=?,status=? WHERE id=?', (report['id'], 'RECEIVED', event_id))
    try:
        operations.dispatch(report['id'], actor='SOS_DEMO_AUTOMATION')
        status = 'DEMO_MISSION_ASSIGNED'
    except ValueError:
        status = 'AWAITING_AVAILABLE_DEMO_UNIT'
    with db.get_connection() as conn:
        conn.execute('UPDATE distress SET status=? WHERE id=?', (status, event_id))


@router.post('/distress')
def create_distress(request: DistressRequest):
    payload = request.model_dump()
    signature = delivery.fingerprint(payload)
    with db.WRITE_LOCK, db.get_connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        old = conn.execute('SELECT * FROM distress WHERE id=?', (request.client_request_id,)).fetchone()
        if old and not hmac.compare_digest(old['request_hash'], signature):
            raise HTTPException(409, 'This receipt ID belongs to a different signal.')
        if not old:
            conn.execute('INSERT INTO distress (id,request_hash,tracking_token,kind,payload,created_at,status) VALUES (?,?,?,?,?,?,?)',
                (request.client_request_id, signature, secrets.token_urlsafe(32), request.kind, json.dumps(payload),
                 db.now_iso(), 'LOCATION_NEEDED' if request.latitude is None else 'AWAITING_REVIEW'))
    materialize(request.client_request_id)
    return view(get_row(request.client_request_id), True)


@router.get('/distress')
def list_distress():
    with db.get_connection() as conn:
        return [view(r) for r in conn.execute('SELECT * FROM distress ORDER BY created_at DESC LIMIT 100')]


def authorize_event(request, row):
    from command_auth import require_authority
    try:
        require_authority(request)
        return
    except ValueError:
        pass
    if not row or not hmac.compare_digest(row['tracking_token'], request.headers.get('X-Report-Token', '')):
        raise HTTPException(401, 'Open the signal from your saved receipt.')


@router.get('/distress/{event_id}')
def distress_receipt(event_id: str, request: Request):
    row = get_row(event_id)
    authorize_event(request, row)
    result = view(row)
    if row['report_id']:
        result['report_receipt'] = delivery.receipt(db.get_report(row['report_id']))
    return result


@router.get('/distress/{event_id}/audio')
def distress_audio(event_id: str, request: Request):
    from fastapi.responses import Response
    row = get_row(event_id)
    authorize_event(request, row)
    audio = json.loads(row['payload']).get('audio')
    if not audio:
        raise HTTPException(404, 'No recording attached.')
    return Response(base64.b64decode(audio), media_type='audio/webm', headers={'Cache-Control': 'no-store'})


class Review(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    incident_type: Literal['Fire', 'Flood', 'Landslide', 'Accident'] | None = None
    people_affected: int = Field(default=0, ge=0, le=1000000)
    resource_type: Literal['POLICE', 'AMBULANCE', 'FIRE_ENGINE', 'RESCUE_TEAM'] | None = None


@router.patch('/distress/{event_id}')
def review_distress(event_id: str, review: Review):
    row = get_row(event_id)
    if not row:
        raise HTTPException(404, 'Signal not found.')
    if (review.latitude is None) != (review.longitude is None):
        raise HTTPException(422, 'Provide both coordinates.')
    if review.latitude is not None and not row['report_id']:
        payload = json.loads(row['payload'])
        payload.update(latitude=review.latitude, longitude=review.longitude, location='Authority-confirmed signal location')
        with db.get_connection() as conn:
            conn.execute('UPDATE distress SET payload=? WHERE id=?', (json.dumps(payload), event_id))
        materialize(event_id)
    row = get_row(event_id)
    if row['kind'] == 'VOICE' and review.incident_type and not row['report_id']:
        payload = json.loads(row['payload'])
        if payload['latitude'] is None:
            raise HTTPException(422, 'Confirm the incident location before creating a reviewed report.')
        report = operations.submit(dict(client_request_id='distress_' + event_id, source='APP',
            incident_type=review.incident_type, location=payload['location'] or 'Authority reviewed voice location',
            latitude=payload['latitude'], longitude=payload['longitude'], people_affected=review.people_affected,
            hazard_intensity=0.2, description=row['transcript'] or payload['text'] or 'Recorded voice awaiting full interpretation.',
            raw_content=row['transcript'] or payload['text'], vulnerable_groups=[]))
        with db.get_connection() as conn:
            conn.execute('UPDATE distress SET report_id=?,status=? WHERE id=?', (report['id'], 'REVIEWED_AWAITING_APPROVAL', event_id))
            db._insert_audit_event(conn, report_id=report['id'], fusion_id=report['fusion_id'], event_type='VOICE_REVIEWED',
                actor='AUTHORITY', message='Authority classified retained voice; normal dispatch still requires approval.', metadata={'distress_id': event_id})
        row = get_row(event_id)
    if review.resource_type and row['report_id']:
        try:
            operations.dispatch(row['report_id'], additional_type=review.resource_type)
        except ValueError as error:
            raise HTTPException(409, str(error)) from None
    return view(get_row(event_id))


async def process_pending():
    # Restart-safe retries. Single uvicorn worker is the supported local deployment.
    while True:
        await asyncio.sleep(20)
        if not api_key('SARVAM_API_KEY'):
            continue
        with db.get_connection() as conn:
            rows = conn.execute("SELECT * FROM distress WHERE kind='VOICE' AND transcript IS NULL AND attempts<3 AND next_attempt<? LIMIT 2", (time.time(),)).fetchall()
        for row in rows:
            payload = json.loads(row['payload'])
            if not payload.get('audio'):
                continue
            with db.get_connection() as conn:
                conn.execute('UPDATE distress SET attempts=attempts+1,next_attempt=? WHERE id=?',
                             (time.time() + 60 * 2 ** row['attempts'], row['id']))
            try:
                result = await SarvamSpeechProvider().transcribe(base64.b64decode(payload['audio']), 'audio/webm')
                with db.get_connection() as conn:
                    conn.execute('UPDATE distress SET transcript=?,status=? WHERE id=?',
                                 (result.transcript, 'AWAITING_REVIEW', row['id']))
            except SpeechUnavailable:
                pass  # Original audio stays available to Command and its receipt owner.
