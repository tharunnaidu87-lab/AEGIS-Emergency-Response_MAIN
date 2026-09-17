"""
AEGIS local demonstration preflight.

Checks whether the local AEGIS project has the important
files and demo components required before startup.

This script:
- does NOT contact real emergency services
- does NOT modify project files
- does NOT dispatch any real resource
"""

from __future__ import annotations

import json
import shutil
import socket
import sys
from pathlib import Path


# ============================================================
# PROJECT ROOT
# ============================================================

ROOT = Path(__file__).resolve().parents[1]


# ============================================================
# RESULT COLLECTION
# ============================================================

errors: list[str] = []
warnings: list[str] = []
passed: list[str] = []


def ok(message: str) -> None:
    passed.append(message)


def fail(message: str) -> None:
    errors.append(message)


def warn(message: str) -> None:
    warnings.append(message)


# ============================================================
# FILE HELPERS
# ============================================================

def require_file(
    path: str,
    label: str | None = None,
) -> Path:

    target = ROOT / path

    if target.is_file():
        ok(label or path)

    else:
        fail(f"Missing file: {path}")

    return target


def require_directory(
    path: str,
) -> Path:

    target = ROOT / path

    if target.is_dir():
        ok(f"Directory: {path}")

    else:
        fail(f"Missing directory: {path}")

    return target


def require_text(
    file_path: Path,
    marker: str,
    label: str,
) -> None:

    if not file_path.exists():
        return

    try:
        content = file_path.read_text(
            encoding="utf-8"
        )

    except Exception as error:
        fail(
            f"Unable to inspect {file_path.name}: {error}"
        )
        return

    if marker in content:
        ok(label)

    else:
        fail(
            f"{label} marker missing from "
            f"{file_path.relative_to(ROOT)}"
        )


# ============================================================
# PORT CHECK
# ============================================================

def port_available(
    port: int,
) -> bool:

    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    )

    try:
        sock.bind(
            (
                "127.0.0.1",
                port,
            )
        )

        return True

    except OSError:
        return False

    finally:
        sock.close()


# ============================================================
# BASIC PROJECT STRUCTURE
# ============================================================

require_directory("backend")
require_directory("frontend")
require_directory("data")
require_directory("scripts")


# ============================================================
# BACKEND FILES
# ============================================================

backend_main = require_file(
    "backend/main.py"
)

require_file(
    "backend/db.py"
)

require_file(
    "backend/models.py"
)

require_file(
    "backend/operations.py"
)

require_file(
    "backend/command_auth.py"
)

require_file(
    "backend/distress.py"
)

require_file(
    "backend/intake_delivery.py"
)

require_file(
    "backend/provider_health.py"
)

require_file(
    "backend/request_guard.py"
)

require_file(
    "backend/engines/aegis_engine.py"
)

require_file(
    "backend/engines/resource_engine.py"
)

require_file(
    "backend/tests/test_aegis.py"
)

require_file(
    "backend/tests/test_intake.py"
)

require_file(
    "backend/tests/test_voice.py"
)

require_file(
    "backend/tests/test_resilience.py"
)


# ============================================================
# FRONTEND FILES
# ============================================================

app_file = require_file(
    "frontend/src/App.tsx"
)

require_file(
    "frontend/src/api.ts"
)

require_file(
    "frontend/src/OperationalMap.tsx"
)

require_file(
    "frontend/src/IncidentLifecycle.tsx"
)

require_file(
    "frontend/src/outbox.ts"
)

require_file(
    "frontend/src/DeliveryUI.tsx"
)

require_file(
    "frontend/src/DistressPanel.tsx"
)

require_file(
    "frontend/src/PhotoPicker.tsx"
)

require_file(
    "frontend/src/ReportPhotos.tsx"
)

require_file(
    "frontend/src/CommandAuthBoundary.tsx"
)

require_file(
    "frontend/src/commandAuthFetch.ts"
)

require_file(
    "frontend/src/resilience.css"
)

require_file(
    "frontend/src/main.tsx"
)

require_file(
    "frontend/package.json"
)

require_file(
    "frontend/vite.config.ts"
)

require_file(
    "frontend/public/manifest.webmanifest"
)

service_worker = require_file(
    "frontend/public/sw.js"
)


# ============================================================
# DEMO DATA
# ============================================================

resource_file = require_file(
    "data/resources.json"
)

require_file(
    "data/habitations.json"
)

require_file(
    "data/hospitals.json"
)

require_file(
    "data/relocation_centres.json"
)


# ============================================================
# PYTHON ENVIRONMENT
# ============================================================

python_exe = (
    ROOT
    / "backend"
    / ".venv"
    / "Scripts"
    / "python.exe"
)


if python_exe.exists():
    ok("Backend Python virtual environment")

else:
    fail(
        "backend/.venv/Scripts/python.exe is missing"
    )


# ============================================================
# NODE / NPM
# ============================================================

node = shutil.which(
    "node"
)


npm = (
    shutil.which("npm.cmd")
    or shutil.which("npm")
)


if node:
    ok("Node.js available")

else:
    fail(
        "Node.js was not found in PATH"
    )


if npm:
    ok("npm available")

else:
    fail(
        "npm was not found in PATH"
    )


# ============================================================
# RESOURCE CATALOGUE VALIDATION
# ============================================================

if resource_file.exists():

    try:

        resources = json.loads(
            resource_file.read_text(
                encoding="utf-8"
            )
        )


        if not isinstance(
            resources,
            list,
        ):
            raise ValueError(
                "resources.json must contain a JSON list"
            )


        if not resources:

            fail(
                "Demo resource catalogue is empty"
            )

        else:

            identifiers = [
                str(
                    item.get(
                        "id",
                        ""
                    )
                ).strip()
                for item in resources
                if isinstance(
                    item,
                    dict,
                )
            ]


            if len(identifiers) != len(resources):

                fail(
                    "One or more demo resources "
                    "are not valid JSON objects"
                )

            elif any(
                not identifier
                for identifier in identifiers
            ):

                fail(
                    "One or more demo resources "
                    "are missing an ID"
                )

            elif (
                len(identifiers)
                !=
                len(set(identifiers))
            ):

                fail(
                    "Duplicate demo resource IDs detected"
                )

            else:

                ok(
                    f"{len(resources)} "
                    "simulated resources loaded"
                )


                resource_types = {
                    str(
                        item.get(
                            "type",
                            ""
                        )
                    ).upper()
                    for item in resources
                    if isinstance(
                        item,
                        dict,
                    )
                }


                if any(
                    "POLICE" in resource_type
                    for resource_type in resource_types
                ):

                    ok(
                        "Simulated police resource available"
                    )

                else:

                    warn(
                        "No simulated police resource "
                        "was detected for SOS demo"
                    )


    except Exception as error:

        fail(
            f"resources.json invalid: {error}"
        )


# ============================================================
# IMPORTANT APP FEATURES
# ============================================================

if app_file.exists():

    try:

        app = app_file.read_text(
            encoding="utf-8"
        )


        expected = {
            "Authority dispatch gate":
                "APPROVE RESPONSE & DISPATCH",

            "Demo movement":
                "START DEMO MOVEMENT",

            "SOS UI":
                "SosButton",

            "Photo evidence":
                "PhotoPicker",

            "Offline delivery":
                "queueReport",

            "Lifecycle UI":
                "IncidentLifecycle",

            "Responder page":
                "ResponderPage",

            "Command page":
                "CommandPage",
        }


        for label, marker in expected.items():

            if marker in app:
                ok(label)

            else:
                fail(
                    f"{label} marker "
                    "missing from App.tsx"
                )


        if (
            "publicReportStatus(selected.status)"
            in app
        ):

            ok(
                "Authority approval status display"
            )

        else:

            warn(
                "Could not confirm Command Center "
                "authority approval status display"
            )


    except Exception as error:

        fail(
            f"Unable to inspect App.tsx: {error}"
        )


# ============================================================
# SERVICE WORKER / OFFLINE SUPPORT
# ============================================================

if service_worker.exists():

    try:

        worker = service_worker.read_text(
            encoding="utf-8"
        )


        if (
            "aegis-outbox" in worker
        ):

            ok(
                "Service worker knows AEGIS outbox"
            )

        else:

            fail(
                "Service worker does not contain "
                "the AEGIS outbox sync tag"
            )


        has_sync_listener = (
            'addEventListener("sync"' in worker
            or "addEventListener('sync'" in worker
            or '"sync",' in worker
            or "'sync'," in worker
        )


        if has_sync_listener:

            ok(
                "Background Sync handler"
            )

        else:

            fail(
                "Service worker Background "
                "Sync handler missing"
            )


        if (
            "isApiRequest" in worker
            or '"/api"' in worker
            or '"/api/"' in worker
        ):

            ok(
                "Service worker API handling present"
            )

        else:

            warn(
                "Could not confirm API cache protection"
            )


    except Exception as error:

        fail(
            f"Unable to inspect sw.js: {error}"
        )


# ============================================================
# BACKEND FEATURE MARKERS
# ============================================================

if backend_main.exists():

    try:

        backend_text = backend_main.read_text(
            encoding="utf-8"
        )


        backend_markers = {
            "Report API":
                "/reports",

            "AEGIS analysis API":
                "/aegis-analyse",

            "Distress/SOS backend":
                "distress",
        }


        for label, marker in backend_markers.items():

            if marker in backend_text:

                ok(label)

            else:

                warn(
                    f"Could not confirm {label} "
                    "in backend/main.py"
                )


    except Exception as error:

        fail(
            f"Unable to inspect backend/main.py: {error}"
        )


# ============================================================
# PORTS
# ============================================================

for port, label in [
    (
        8001,
        "Backend",
    ),
    (
        5173,
        "Frontend",
    ),
]:

    if port_available(
        port
    ):

        ok(
            f"{label} port {port} available"
        )

    else:

        warn(
            f"{label} port {port} "
            "is already in use"
        )


# ============================================================
# CHROME / EDGE
# ============================================================

chrome_locations = [
    Path(
        r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    ),
    Path(
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    ),
]


edge_locations = [
    Path(
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    ),
    Path(
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
    ),
]


if any(
    location.exists()
    for location in chrome_locations
):

    ok(
        "Google Chrome available"
    )

elif any(
    location.exists()
    for location in edge_locations
):

    ok(
        "Microsoft Edge available"
    )

else:

    warn(
        "Chrome/Edge was not found "
        "at standard Windows locations"
    )


# ============================================================
# STARTUP SCRIPT
# ============================================================

start_demo = ROOT / "scripts" / "Start-Demo.ps1"


if start_demo.exists():

    ok(
        "Demo startup script"
    )

else:

    warn(
        "scripts/Start-Demo.ps1 is missing"
    )


# ============================================================
# RESULT
# ============================================================

print()
print(
    "=" * 68
)

print(
    "AEGIS DEMO PREFLIGHT"
)

print(
    "=" * 68
)


for message in passed:

    print(
        f"[ OK ] {message}"
    )


for message in warnings:

    print(
        f"[WARN] {message}"
    )


for message in errors:

    print(
        f"[FAIL] {message}"
    )


print(
    "-" * 68
)


print(
    f"PASS : {len(passed)}"
)

print(
    f"WARN : {len(warnings)}"
)

print(
    f"FAIL : {len(errors)}"
)


if errors:

    print()
    print(
        "AEGIS IS NOT READY FOR DEMO."
    )

    print(
        "Fix the FAIL items above "
        "and run this preflight again."
    )

    sys.exit(
        1
    )


print()
print(
    "AEGIS PREFLIGHT PASSED."
)

print(
    "All emergency resources remain "
    "SIMULATED / DEMO-ONLY."
)

print(
    "No real police, ambulance, fire, "
    "112, NDRF or SDRF service is contacted."
)

sys.exit(
    0
)