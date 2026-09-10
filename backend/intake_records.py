"""Server-owned, short-lived previews; no reports/assignments until confirmation."""
import json
import time
import uuid
import db


def save_preview(kind, data):
    identifier = uuid.uuid4().hex
    with db.WRITE_LOCK, db.get_connection() as connection:
        connection.execute("DELETE FROM intake_previews WHERE created_at < ?", (time.time() - 86400,))
        connection.execute("INSERT INTO intake_previews VALUES (?,?,?,?)",
                           (identifier, kind, json.dumps(data), time.time()))
    return identifier


def get_preview(identifier, kind):
    with db.get_connection() as connection:
        row = connection.execute("SELECT payload_json FROM intake_previews WHERE id=? AND kind=? AND created_at>=?",
                                 (identifier, kind, time.time() - 86400)).fetchone()
    if row is None:
        raise ValueError("This voice/intake preview expired or is unavailable. Analyze the transcript again.")
    return json.loads(row[0])


def speech_metadata(request):
    if request.speech_result_id:
        if request.source != "CALL":
            raise ValueError("Speech metadata requires a CALL report")
        speech = get_preview(request.speech_result_id, "speech")
        return {"speech_provider": speech["provider"], "speech_model": speech["model"],
                "detected_language": speech["language_code"], "original_transcript": speech["transcript"]}
    return {"speech_provider": "BROWSER_SPEECH_RECOGNITION" if request.browser_transcript else "MANUAL_TEXT",
            "speech_model": None, "detected_language": None,
            "browser_language_hint": request.browser_language if request.browser_transcript else None,
            "original_transcript": request.browser_transcript or request.text}
