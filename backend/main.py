"""Compatible FastAPI endpoints for the shared AEGIS prototype."""
import os
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from provider_config import api_key, SARVAM_MODEL, NVIDIA_MODEL
from command_auth import CommandAuthMiddleware, router as command_auth_router
import db
import operations
from intake_nlp import Extraction, ParseRequest
from intake_records import save_preview, speech_metadata
from nlp.router import extract
from speech.sarvam import SarvamSpeechProvider
from speech.provider import SpeechUnavailable, Transcription
from models import AnalysisRequest, Coordinates, ReportCreateRequest
from engines.capacity_engine import calculate_all_centres
from engines.relocation_engine import create_relocation_plan
from engines.risk_engine import analyse_habitations
from engines.resource_engine import load_resources


@asynccontextmanager
async def lifespan(app):
    db.init_db()
    operations.upgrade_legacy_analyses()
    yield


app = FastAPI(title="AEGIS Backend", version="5.0", lifespan=lifespan)
app.add_middleware(CommandAuthMiddleware)
app.add_middleware(CORSMiddleware,
    allow_origins=[s.strip() for s in os.getenv("AEGIS_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if s.strip()],
    allow_credentials=False, allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type", "Authorization"])
app.include_router(command_auth_router)


def found(value, label="Report"):
    if value is None:
        raise HTTPException(404, f"{label} not found")
    return value


def conflict(action):
    try:
        return action()
    except (ValueError, RuntimeError) as error:
        raise HTTPException(409, str(error)) from error


@app.get("/")
def home():
    return {"system": "AEGIS", "status": "ONLINE", "version": "5.0", "database": "SQLite",
            "mode": "LOCAL_DEMO_DECISION_SUPPORT"}


@app.get("/health")
def health():
    with db.get_connection() as connection:
        connection.execute("SELECT count(*) FROM reports").fetchone()
    return {"status": "HEALTHY", "backend": "ONLINE", "database": "CONNECTED"}


@app.post("/aegis-analyse")
def aegis_analyse(request: AnalysisRequest):
    with db.get_connection() as connection:
        report = found(db.get_report(request.report_id)) if request.report_id else None
        busy = operations.busy_ids(connection, report["fusion_id"] if report else None)
    return {"status": "AEGIS_ANALYSIS_COMPLETE",
            "result": operations.calculate(request.model_dump(), unavailable=busy, evidence=db.list_fusion_reports(report["fusion_id"]) if report else None)}


@app.post("/incident")
def create_incident(request: AnalysisRequest):
    result = aegis_analyse(request)["result"]
    return {"status": "INCIDENT_RECEIVED", "incident": {**result["incident"], "people_affected": request.people_affected},
            "analysis": result["severity_analysis"], "resource_plan": result["resource_plan"], "hospital_plan": result["hospital_plan"]}


@app.get("/relocation-centres")
def relocation_centres():
    centres = calculate_all_centres()
    return {"status": "CAPACITY_ANALYSIS_COMPLETE", "total_centres": len(centres), "centres": centres}


class RelocationRequest(Coordinates):
    people_to_relocate: int = Field(ge=0, le=1000000)


@app.post("/relocation-plan")
def relocation_plan(request: RelocationRequest):
    return {"status": "RELOCATION_PLAN_GENERATED",
            "plan": create_relocation_plan(request.people_to_relocate, request.latitude, request.longitude)}


class HazardAnalysisRequest(Coordinates):
    incident_type: Literal["Flood", "Landslide", "Fire", "Accident"]
    hazard_intensity: float = Field(ge=0, le=1)


@app.post("/hazard-analysis")
def hazard_analysis(request: HazardAnalysisRequest):
    return {"status": "HAZARD_ANALYSIS_COMPLETE", "analysis": analyse_habitations(
        request.incident_type, request.latitude, request.longitude, request.hazard_intensity)}


@app.get("/resources")
def resources():
    with db.get_connection() as connection:
        busy = operations.busy_ids(connection)
    return {"status": "RESOURCE_CATALOG", "source": "LOCAL_DEMO",
            "resources": [{**r, "status": "BUSY" if r["id"] in busy else r["status"]} for r in load_resources()]}


@app.post("/reports")
def submit_report(request: ReportCreateRequest):
    report = conflict(lambda: operations.submit(request.model_dump()))
    return {"status": "REPORT_STORED", "fusion_id": report["fusion_id"], "report": report}


@app.post("/intake/parse", response_model=Extraction)
async def parse_emergency_intake(request: ParseRequest):
    speech = conflict(lambda: speech_metadata(request))
    result = await extract(request)
    result.result_id = save_preview("nlp", {"source": request.source, "text": request.text,
        "extraction": result.model_dump(), "speech": speech})
    return result


@app.post("/voice/transcribe", response_model=Transcription)
async def transcribe_voice(request: Request):
    content_type = request.headers.get("content-type", "").lower()
    if content_type.split(";", 1)[0] != "audio/webm":
        raise HTTPException(415, "Record WebM/Opus audio, or use browser speech/manual text.")
    audio = bytearray()
    async for chunk in request.stream():
        if len(audio) + len(chunk) > 5 * 1024 * 1024:
            raise HTTPException(413, "Recording is too large. Record up to 25 seconds and retry.")
        audio.extend(chunk)
    if not audio:
        raise HTTPException(422, "No audio was recorded. Please retry.")
    try:
        result = await SarvamSpeechProvider().transcribe(bytes(audio), content_type)
    except SpeechUnavailable as error:
        raise HTTPException(503, str(error)) from None
    result.result_id = save_preview("speech", result.model_dump())
    return result


@app.get("/intake/capabilities")
def intake_capabilities():
    return {"parser": "ADVANCED_NLP" if api_key("NVIDIA_API_KEY") else "LOCAL_RULE_BASED",
            "nlp_model": NVIDIA_MODEL, "language": "auto", "requires_api_key": True,
            "telecom": "PROVIDER_READY_NOT_CONFIGURED", "telephone_number": None,
            "speech": "SARVAM" if api_key("SARVAM_API_KEY") else "BROWSER_CAPABILITY_DEPENDENT",
            "speech_model": SARVAM_MODEL}


@app.get("/reports")
def reports(limit: int = Query(100, ge=1, le=500)):
    records = db.list_reports(limit)
    return {"status": "REPORT_LIST", "total": len(records), "reports": records}


@app.get("/reports/{report_id}")
def report_by_id(report_id: str):
    return {"status": "REPORT_FOUND", "report": found(db.get_report(report_id))}


@app.get("/fusion/{fusion_id}/reports")
def fusion_reports(fusion_id: str, limit: int = Query(200, ge=1, le=500)):
    records = db.list_fusion_reports(fusion_id, limit)
    if not records:
        raise HTTPException(404, "Fusion group not found")
    return {"status": "FUSION_GROUP_FOUND", "fusion_id": fusion_id, "total": len(records), "reports": records}


class ReportStatusUpdate(BaseModel):
    status: Literal["REPORTED", "ACKNOWLEDGED", "DISPATCHED", "EN_ROUTE", "ON_SCENE", "RESOLVED"]


@app.patch("/reports/{report_id}/status")
def change_report_status(report_id: str, request: ReportStatusUpdate):
    report = conflict(lambda: operations.set_report_status(report_id, request.status))
    return {"status": "REPORT_STATUS_UPDATED", "report": found(report)}


@app.post("/reports/{report_id}/dispatch")
def dispatch_report(report_id: str):
    result = found(conflict(lambda: operations.dispatch(report_id)))
    return {"status": "RESOURCES_DISPATCHED", **result}


@app.get("/assignments")
def assignments(resource_id: str | None = None, report_id: str | None = None,
                limit: int = Query(200, ge=1, le=500)):
    if report_id:
        report = found(db.get_report(report_id))
        report_id = report.get("analysis", {}).get("result", {}).get("fusion", {}).get("canonical_report_id", report_id)
    records = db.list_assignments(resource_id, report_id, limit)
    return {"status": "ASSIGNMENT_LIST", "total": len(records), "assignments": records}


@app.get("/assignments/{assignment_id}")
def assignment_by_id(assignment_id: str):
    return {"status": "ASSIGNMENT_FOUND", "assignment": found(db.get_assignment(assignment_id), "Assignment")}


class AssignmentStatusUpdate(BaseModel):
    status: Literal["ASSIGNED", "ACCEPTED", "EN_ROUTE", "ON_SCENE", "RESOLVED", "ISSUE"]


@app.patch("/assignments/{assignment_id}/status")
def change_assignment_status(assignment_id: str, request: AssignmentStatusUpdate):
    result = conflict(lambda: operations.set_assignment_status(assignment_id, request.status))
    return {"status": "ASSIGNMENT_STATUS_UPDATED", "assignment": found(result, "Assignment")}


class ReassignmentRequest(BaseModel):
    reason: str = Field(default="UNIT_ISSUE", min_length=1, max_length=500)


@app.post("/assignments/{assignment_id}/reassign")
def reassign_failed_assignment(assignment_id: str, request: ReassignmentRequest):
    result = found(conflict(lambda: db.reassign_assignment(assignment_id, reason=request.reason)), "Assignment")
    return {"status": "ASSIGNMENT_ALREADY_REASSIGNED" if result["already_reassigned"] else "ASSIGNMENT_REASSIGNED", **result}


@app.get("/audit-events")
def audit_events(report_id: str | None = None, assignment_id: str | None = None,
                 fusion_id: str | None = None, limit: int = Query(300, ge=1, le=1000)):
    events = db.list_audit_events(report_id, assignment_id, fusion_id, limit)
    return {"status": "AUDIT_EVENT_LIST", "total": len(events), "events": events}


@app.post("/demo/reset")
def reset_demo_reports():
    if os.getenv("AEGIS_ENABLE_RESET", "false").lower() != "true":
        raise HTTPException(403, "Demo reset is disabled. Use a separate demo database.")
    return {"status": "DEMO_REPORTS_CLEARED", "deleted": db.clear_reports()}
