"""Two-phase check that a public AEGIS report survives a Render restart."""
import argparse
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = ROOT / ".cache" / "render-persistence-check.json"


def request_json(url, *, payload=None, token=None):
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["X-Report-Token"] = token
    request = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"AEGIS returned HTTP {error.code}.") from None


def safe_state_path(value):
    path = Path(value).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("State file must stay inside AEGIS-MAIN.")
    return path


def create(base_url, state_path):
    health = request_json(base_url + "/health")
    if health.get("database_backend") != "postgresql":
        raise RuntimeError("The deployed backend is not using PostgreSQL.")
    client_id = "render-persist-" + uuid.uuid4().hex[:20]
    receipt = request_json(
        base_url + "/reports",
        payload={
            "client_request_id": client_id,
            "incident_type": "Accident",
            "location": "PERSISTENCE TEST - DO NOT DISPATCH",
            "latitude": 13.0827,
            "longitude": 80.2707,
            "people_affected": 0,
            "hazard_intensity": 0,
            "description": "Automated Render restart persistence verification.",
        },
    )
    state = {
        "base_url": base_url,
        "report_id": receipt["report"]["id"],
        "fusion_id": receipt["fusion_id"],
        "tracking_token": receipt["tracking_token"],
        "client_request_id": client_id,
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"Created {state['report_id']}. Restart or redeploy the backend, then run verify.")


def verify(state_path):
    state = json.loads(state_path.read_text(encoding="utf-8"))
    report = request_json(
        state["base_url"] + "/reports/" + state["report_id"],
        token=state["tracking_token"],
    )["report"]
    if report["id"] != state["report_id"] or report["fusion_id"] != state["fusion_id"]:
        raise RuntimeError("The stored report identity changed after restart.")
    health = request_json(state["base_url"] + "/health")
    if health.get("database_backend") != "postgresql":
        raise RuntimeError("The restarted backend is not using PostgreSQL.")
    print(f"PASS: {report['id']} survived the backend restart on PostgreSQL.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("create", "verify"))
    parser.add_argument("--url", help="Deployed backend URL for the create phase")
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    args = parser.parse_args()
    state = safe_state_path(args.state)
    if args.action == "create":
        if not args.url:
            parser.error("--url is required for create")
        create(args.url.rstrip("/"), state)
    else:
        verify(state)


if __name__ == "__main__":
    main()

