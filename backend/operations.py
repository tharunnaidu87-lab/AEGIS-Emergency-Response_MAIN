"""Persistent operations. SQLite transactions protect assignments across requests."""
import json
from collections import Counter
import db
from engines.aegis_engine import run_aegis_analysis

ACTIVE = ("ASSIGNED", "ACCEPTED", "EN_ROUTE", "ON_SCENE", "ISSUE")
ASSIGNMENT_NEXT = {
    "ASSIGNED": {"ACCEPTED", "EN_ROUTE", "ISSUE"},
    "ACCEPTED": {"EN_ROUTE", "ISSUE"},
    "EN_ROUTE": {"ON_SCENE", "ISSUE"},
    "ON_SCENE": {"RESOLVED", "ISSUE"},
    "ISSUE": set(), "RESOLVED": set(),
}
REPORT_ORDER = ["REPORTED", "ACKNOWLEDGED", "DISPATCHED", "EN_ROUTE", "ON_SCENE", "RESOLVED"]


def busy_ids(connection, fusion_id=None):
    rows = connection.execute(
        "SELECT a.resource_id, r.fusion_id FROM assignments a JOIN reports r ON r.id=a.report_id WHERE a.status != 'RESOLVED'"
    ).fetchall()
    return {r["resource_id"] for r in rows if r["fusion_id"] != fusion_id}


def calculate(payload, *, unavailable=None, evidence=None):
    return run_aegis_analysis(payload["incident_type"], payload["location"], payload["latitude"],
        payload["longitude"], payload["people_affected"], payload.get("description", ""),
        payload.get("hazard_intensity", .5), injured=payload.get("injured", 0), trapped=payload.get("trapped", 0),
        vulnerable_groups=payload.get("vulnerable_groups", []), gps_verified=payload.get("gps_verified", False),
        spreading=payload.get("spreading", False), structural_damage=payload.get("structural_damage", False),
        scenario=payload.get("scenario", {}), unavailable_ids=unavailable, evidence=evidence)


def aggregate(group):
    # Overlapping reports are observations of one incident, so count maxima, never sum duplicates.
    first = group[0]
    payload = dict(first)
    for key in ("people_affected", "hazard_intensity", "injured", "trapped"):
        payload[key] = max(r.get(key, 0) for r in group)
    for key in ("spreading", "structural_damage", "gps_verified"):
        payload[key] = any(r.get(key) for r in group)
    payload["vulnerable_groups"] = sorted({g for r in group for g in r["vulnerable_groups"]})
    payload["description"] = max((r["description"] for r in group), key=len)
    return payload


def refresh_fusion(connection, fusion_id):
    rows = connection.execute("SELECT * FROM reports WHERE fusion_id=? ORDER BY created_at", (fusion_id,)).fetchall()
    group = [db.decode_report(r) for r in rows]
    result = calculate(aggregate(group), unavailable=busy_ids(connection, fusion_id), evidence=group)
    result["fusion"] = {"id": fusion_id, "canonical_report_id": group[0]["id"],
                        "report_ids": [r["id"] for r in group], "report_count": len(group),
                        "population_method": "MAX_OBSERVATION_NOT_SUM"}
    envelope = {"status": "AEGIS_ANALYSIS_COMPLETE", "result": result}
    connection.execute("UPDATE reports SET analysis_json=? WHERE fusion_id=?", (json.dumps(envelope), fusion_id))
    return group, envelope


def upgrade_legacy_analyses():
    """Refresh old calculation envelopes once, retaining their original result in audit history."""
    with db.WRITE_LOCK, db.get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute("SELECT * FROM reports ORDER BY created_at").fetchall()
        legacy_groups = {row["fusion_id"] for row in rows
                         if not json.loads(row["analysis_json"]).get("result", {}).get("pipeline")}
        for fusion_id in legacy_groups:
            for row in rows:
                if row["fusion_id"] == fusion_id:
                    db._insert_audit_event(connection, report_id=row["id"], fusion_id=fusion_id,
                        event_type="ANALYSIS_UPGRADED", actor="SYSTEM",
                        message="Legacy calculation upgraded; original report and assignments preserved.",
                        metadata={"previous_analysis": json.loads(row["analysis_json"])})
            refresh_fusion(connection, fusion_id)
        return len(legacy_groups)


def submit(payload):
    # Preserve the existing report schema and audit/fusion repository.
    with db.WRITE_LOCK:
        report = db.create_report(payload, {"status": "AEGIS_ANALYSIS_COMPLETE", "result": calculate(payload)})
        with db.get_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("UPDATE reports SET injured=?, trapped=? WHERE id=?",
                               (payload.get("injured", 0), payload.get("trapped", 0), report["id"]))
            group, _ = refresh_fusion(connection, report["fusion_id"])
            status = max((r["status"] for r in group), key=REPORT_ORDER.index)
            connection.execute("UPDATE reports SET status=? WHERE fusion_id=?", (status, report["fusion_id"]))
    return db.get_report(report["id"])


def dispatch(report_id):
    with db.WRITE_LOCK, db.get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
        if row is None:
            return None
        report = db.decode_report(row)
        if report["status"] == "RESOLVED":
            raise ValueError("Resolved incidents cannot be dispatched")
        group, envelope = refresh_fusion(connection, report["fusion_id"])
        canonical = group[0]["id"]
        existing = connection.execute(
            "SELECT a.* FROM assignments a JOIN reports r ON r.id=a.report_id WHERE r.fusion_id=?",
            (report["fusion_id"],)).fetchall()
        # Idempotent dispatch, including another report describing the same incident.
        if existing:
            return {"report": db.decode_report(connection.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()),
                    "assignments": [dict(a) for a in existing], "already_dispatched": True}
        resources = envelope["result"]["resource_plan"]["selected_resources"]
        if not resources:
            raise ValueError("No compatible available units. Review shortages before dispatch.")
        timestamp = db.now_iso()
        for resource in resources:
            assignment_id = db.generate_assignment_id()
            connection.execute(
                """INSERT INTO assignments
                (id,report_id,resource_id,resource_name,resource_type,start_latitude,start_longitude,
                 distance_km,eta_minutes,status,assigned_at,updated_at)
                 VALUES (?,?,?,?,?,?,?,?,?,'ASSIGNED',?,?)""",
                (assignment_id,canonical,resource["id"],resource["name"],resource["type"],
                 resource["latitude"],resource["longitude"],resource["distance_km"],
                 resource["eta_minutes"],timestamp,timestamp))
            db._insert_audit_event(connection, report_id=canonical, assignment_id=assignment_id,
                fusion_id=report["fusion_id"], event_type="ASSIGNMENT_CREATED", actor="COMMAND",
                message=f"{resource['id']} assigned. {resource['selection_reason']}",
                metadata={"eta_basis": "DISTANCE_ESTIMATE", "resource_id": resource["id"]})
        _set_group_status(connection, report["fusion_id"], "DISPATCHED", "COMMAND")
        rows = connection.execute("SELECT * FROM assignments WHERE report_id=?", (canonical,)).fetchall()
        report = db.decode_report(connection.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone())
        return {"report": report, "assignments": [dict(a) for a in rows], "already_dispatched": False}


def _set_group_status(connection, fusion_id, status, actor):
    current = connection.execute("SELECT id,status FROM reports WHERE fusion_id=?", (fusion_id,)).fetchall()
    for row in current:
        if row["status"] != status:
            connection.execute("UPDATE reports SET status=?, updated_at=? WHERE id=?", (status, db.now_iso(), row["id"]))
            db._insert_audit_event(connection, report_id=row["id"], fusion_id=fusion_id,
                event_type="REPORT_STATUS_UPDATED", actor=actor,
                message=f"Incident changed from {row['status']} to {status}.",
                metadata={"from_status": row["status"], "to_status": status})


def set_report_status(report_id, status):
    with db.WRITE_LOCK, db.get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        report = connection.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
        if report is None:
            return None
        if status != report["status"]:
            if status != "ACKNOWLEDGED" or report["status"] != "REPORTED":
                raise ValueError("Acknowledge a received report; dispatch and responder actions drive later stages.")
            _set_group_status(connection, report["fusion_id"], status, "COMMAND")
        return db.decode_report(connection.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone())


def set_assignment_status(assignment_id, status):
    with db.WRITE_LOCK, db.get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM assignments WHERE id=?", (assignment_id,)).fetchone()
        if row is None:
            return None
        assignment = dict(row)
        if assignment["replaced_by_assignment_id"]:
            raise ValueError("This assignment was replaced; update the replacement unit.")
        if status == assignment["status"]:
            return assignment  # Idempotent: do not reset EN_ROUTE movement timestamps.
        if status not in ASSIGNMENT_NEXT[assignment["status"]]:
            raise ValueError(f"Cannot change {assignment['status']} to {status}")
        report = connection.execute("SELECT * FROM reports WHERE id=?", (assignment["report_id"],)).fetchone()
        if status == "EN_ROUTE":
            connection.execute("UPDATE assignments SET departed_at=COALESCE(departed_at,?) WHERE id=?", (db.now_iso(), assignment_id))
        connection.execute("UPDATE assignments SET status=?,updated_at=? WHERE id=?",
                           (status, db.now_iso(), assignment_id))
        db._insert_audit_event(connection, report_id=report["id"], assignment_id=assignment_id,
            fusion_id=report["fusion_id"], event_type="ASSIGNMENT_STATUS_UPDATED", actor="RESPONDER",
            message=f"{assignment['resource_id']}: {assignment['status']} -> {status}",
            metadata={"from_status": assignment["status"], "to_status": status})
        active_rows = connection.execute(
            """SELECT a.status FROM assignments a JOIN reports r ON r.id=a.report_id
            WHERE r.fusion_id=? AND a.replaced_by_assignment_id IS NULL""", (report["fusion_id"],)).fetchall()
        states = [r["status"] for r in active_rows]
        aggregate_status = ("RESOLVED" if states and all(s == "RESOLVED" for s in states)
                            else "ON_SCENE" if "ON_SCENE" in states or "RESOLVED" in states
                            else "EN_ROUTE" if "EN_ROUTE" in states else "DISPATCHED")
        # One late departure must not regress an incident where another unit has arrived.
        if REPORT_ORDER.index(aggregate_status) >= REPORT_ORDER.index(report["status"]):
            _set_group_status(connection, report["fusion_id"], aggregate_status, "SYSTEM_SYNC")
        return dict(connection.execute("SELECT * FROM assignments WHERE id=?", (assignment_id,)).fetchone())
