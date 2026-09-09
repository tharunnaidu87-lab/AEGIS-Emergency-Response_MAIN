# AEGIS

**Predictive Emergency Digital Twin & Resource Orchestration System**

AEGIS is a local emergency decision-support prototype for PSS3. A submitted report drives fusion, severity, evidence quality, resource recommendations, dispatch, routes, projected risk, evacuation planning and spare-resource staging. Citizen, command and responder views share persisted incident state.

The existing dark Field-Grid interface is preserved. The active map uses **MapLibre GL and OpenStreetMap tiles**. The working application did not use Leaflet or a configured service worker; their unused dependencies were removed.

## Start the existing project

Use two PowerShell terminals, both at:

```powershell
Set-Location 'C:\Users\DELL\OneDrive\Desktop\AEGIS-MAIN'
```

Terminal 1, backend with a **new empty demo database**:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Aegis.ps1 -Component Backend -FreshDemo
```

Terminal 2, frontend:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Aegis.ps1 -Component Frontend
```

Open **http://127.0.0.1:5173/report**. API health: **http://127.0.0.1:8001/health**. Interactive schemas: **http://127.0.0.1:8001/docs**. Stop each terminal with Ctrl+C.

Omit `-FreshDemo` to use `data/aegis.db`, or the database selected by `AEGIS_DB_PATH`. Fresh demos use uniquely named files inside `.cache`; they never clear saved reports. Command starts in standby until you select a report.

The launcher confines application caches and temporary files to this project. ExecutionPolicy Bypass applies only to that launched process and does not change machine policy.

## Dependencies on a fresh checkout

The supplied workspace already has frontend dependencies and a working Python virtual environment. For a fresh checkout use Python 3.12 and Node compatible with the locked Vite version. Verified versions are recorded in [VERIFICATION.md](VERIFICATION.md).

From the project root:

```powershell
New-Item -ItemType Directory -Force .cache\tmp, .cache\pip, .cache\npm | Out-Null
$env:TEMP = "$PWD\.cache\tmp"
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = "$PWD\.cache\pip"
$env:npm_config_cache = "$PWD\.cache\npm"
$env:PYTHONDONTWRITEBYTECODE = '1'
py -3.12 -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -B -m pip install -r backend\requirements-dev.txt
npm.cmd --prefix frontend ci
```

Use `requirements.txt` if browser verification is unnecessary. Downloads require internet. A fresh registry download was unavailable in the restricted verification environment; existing dependencies, an offline lockfile update and a production build were checked.

## Configuration

| Variable | Default and purpose |
| --- | --- |
| `AEGIS_DB_PATH` | `data/aegis.db`, relative to the project root; outside-project paths are rejected |
| `AEGIS_BACKEND_URL` | Vite dev proxy target: `http://127.0.0.1:8001` |
| `AEGIS_CORS_ORIGINS` | Comma-separated local frontend origins; set explicit origins for separate production hosting |
| `AEGIS_ENABLE_RESET` | `false`; optional destructive reset is disabled |
| `VITE_API_BASE_URL` | `/api`, same-origin frontend requests |
| `VITE_OSRM_URL` | `https://router.project-osrm.org`, or a compatible driving-route service |

Backend variables are **shell environment variables**; FastAPI does not automatically load `backend/.env`. Example files document values. Vite reads `frontend/.env.local`; VITE values are public build-time settings, never credentials.

No paid services or API keys are required. OSRM and OSM tiles require connectivity. Routing failure produces a labeled straight line; tile failure leaves operational layers over a dark background.

## Verification

After local cache setup above, run from the root:

```powershell
.\backend\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -v
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend test
.\backend\.venv\Scripts\python.exe -B scripts/browser_smoke.py
```

The Windows browser check uses installed Chrome, Node and local Python; ports 8002, 5174 and 9222 must be free. It starts isolated servers and a new database, saves screenshots/logs in `.cache/verification` and closes its processes. Its Chrome flags disable Chrome's internal sandbox for this restricted automation environment; the filesystem boundary remains in effect.

## Deployment preparation

Build with `npm.cmd --prefix frontend run build`. Serve `frontend/dist` with SPA fallback to `index.html` and reverse-proxy `/api/*` to FastAPI, stripping the prefix. For separate origins, set `VITE_API_BASE_URL` before building and configure backend CORS. Vite's development proxy is not a production proxy.

Use HTTPS for GPS, persistent database storage inside the deployed project and backups. The prototype has **no authentication or role authorization**; add those before public operational deployment. Nothing was published and no external accounts were changed.

## Learn and present the project

Voice and text reporting are available from the online form's reporting-method selector. They use backend local NLP, editable review, browser GPS and the same report/Command pipeline. See [INTAKE_HANDOVER.md](INTAKE_HANDOVER.md) for examples, exact changes, deployment settings and test limitations. Restart the backend after this upgrade.

- [ARCHITECTURE.md](ARCHITECTURE.md): files, state ownership, APIs.
- [PROJECT_HANDOVER.md](PROJECT_HANDOVER.md): algorithms and extension points.
- [DEMO_GUIDE.md](DEMO_GUIDE.md): presentation steps and talking points.
- [VERIFICATION.md](VERIFICATION.md): reproducible results and limitations.
