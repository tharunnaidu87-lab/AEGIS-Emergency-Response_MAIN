"""Durable intake receipts and safe media. No real emergency-service connections."""
import base64
import hashlib
import hmac
import io
import json
import secrets
import uuid
import warnings
from PIL import Image, ImageOps
from fastapi import HTTPException, Request
import db


def init_schema():
    with db.WRITE_LOCK, db.get_connection() as conn:
        for name in ('client_request_id', 'request_hash', 'tracking_token'):
            db._ensure_column(conn, 'reports', name, 'TEXT')
        conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS report_client_id ON reports(client_request_id)')
        conn.execute('''CREATE TABLE IF NOT EXISTS report_media (
            id TEXT PRIMARY KEY, report_id TEXT NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
            content BLOB NOT NULL, content_type TEXT NOT NULL)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS distress (
            id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, tracking_token TEXT NOT NULL,
            kind TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
            report_id TEXT, status TEXT NOT NULL, transcript TEXT, attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt REAL NOT NULL DEFAULT 0)''')


def fingerprint(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def existing_report(payload):
    client_id = payload.get('client_request_id')
    if not client_id:
        return None
    with db.get_connection() as conn:
        row = conn.execute('SELECT * FROM reports WHERE client_request_id=?', (client_id,)).fetchone()
    if row:
        if not hmac.compare_digest(row['request_hash'], fingerprint(payload)):
            raise ValueError('This receipt ID belongs to a different report. Start a new report for changed details.')
        return db.decode_report(row)
    return None


def validate_photos(values):
    photos = []
    for encoded in values:
        try:
            raw = base64.b64decode(encoded, validate=True)
            if len(raw) > 700_000:
                raise ValueError('size')
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as probe:
                    if probe.format not in {'JPEG', 'PNG', 'WEBP'} or probe.width * probe.height > 16_000_000:
                        raise ValueError('format or dimensions')
                    probe.verify()
                with Image.open(io.BytesIO(raw)) as picture:
                    picture.load()
                    picture = ImageOps.exif_transpose(picture).convert('RGB')
                    picture.thumbnail((1600, 1600))
                    output = io.BytesIO()
                    picture.save(output, format='JPEG', quality=80)  # strips EXIF and ancillary data
                    photos.append(output.getvalue())
        except Exception:
            raise ValueError('Choose a valid JPEG, PNG or WebP photo smaller than 700 KB after compression.') from None
    return photos


def store_receipt(conn, report_id, payload):
    # Runs in the same transaction as the report INSERT: durable even if its HTTP response is lost.
    conn.execute('UPDATE reports SET client_request_id=?,request_hash=?,tracking_token=? WHERE id=?',
        (payload.get('client_request_id'), fingerprint(payload), secrets.token_urlsafe(32), report_id))
    for photo in validate_photos(payload.get('photos', [])):
        conn.execute('INSERT INTO report_media VALUES (?,?,?,?)', (uuid.uuid4().hex, report_id, photo, 'image/jpeg'))


def receipt(report):
    with db.get_connection() as conn:
        row = conn.execute('SELECT tracking_token FROM reports WHERE id=?', (report['id'],)).fetchone()
    report['photo_ids'] = media_ids(report['id'])
    return {'status': 'REPORT_STORED', 'fusion_id': report['fusion_id'], 'report': report,
            'tracking_token': row['tracking_token']}


def authorize_report(request: Request, report_id):
    from command_auth import validate_command_token, _bearer_token
    try:
        staff = validate_command_token(_bearer_token(request))
        if staff['role'] == 'AUTHORITY':
            return
        with db.get_connection() as conn:
            owned = conn.execute('SELECT 1 FROM assignments WHERE report_id=? AND resource_id=?',
                                 (report_id, staff['sub'])).fetchone()
        if owned:
            return
    except ValueError:
        pass
    with db.get_connection() as conn:
        row = conn.execute('SELECT tracking_token FROM reports WHERE id=?', (report_id,)).fetchone()
    token = request.headers.get('X-Report-Token', '')
    if not row or not row['tracking_token'] or not hmac.compare_digest(row['tracking_token'], token):
        raise HTTPException(401, 'Open this report from your saved receipt.')


def media_ids(report_id):
    with db.get_connection() as conn:
        return [r['id'] for r in conn.execute('SELECT id FROM report_media WHERE report_id=?', (report_id,))]
