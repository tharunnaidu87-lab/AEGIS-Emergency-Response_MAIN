# AEGIS verification record

## 9 September 2026: voice/text upgrade

The combined `scripts/browser_intake_smoke.py` suite passed the existing core flow and all new intake checks. Core regression report: `AEGIS-20260909082708-FF4FD1`, in an isolated verification database. The newest `.cache/verification` artifacts supersede the earlier screenshots below.

- Backend: 34 tests passed, including local parsing, negation, unknowns, review persistence, schema migration, cross-channel fusion and unchanged dispatch.
- Frontend tests: 16 routing assertions plus 12 intake API assertions, including configured production origins and cancellation.
- Final `npm.cmd --prefix frontend run build` and `npm.cmd --prefix frontend run lint`: PASS; zero lint findings. The existing MapLibre vendor-size warning remains. Initial application JavaScript is about 334 kB (101 kB gzip).
- Python compile check: PASS. With `$env:PYTHONPYCACHEPREFIX="$PWD\.cache\intake-pycache"`, ran `.\backend\.venv\Scripts\python.exe -m py_compile backend/main.py backend/models.py backend/db.py backend/operations.py backend/intake_nlp.py backend/telecom/provider.py`. The final backend test rerun passed all 34 tests.
- Intake browser checks: SMS/CALL parsing, correction and submission; tracking and Command originals/source; emulated GPS grant/denial/manual entry; unknown details; processing/submission failures; cold-start feedback; stale response cancellation; unsupported speech; microphone error/no speech/network error/retry; recorder cleanup.
- Speech recognition used simulated browser events. GPS used Chrome emulation and permission controls; no real hardware accuracy or vendor speech-service connection is claimed.
- Final browser log inspection: zero uncaught runtime exceptions, zero console warnings/errors and zero backend/frontend server tracebacks. Expected network errors remain for unavailable map services and deliberately failed requests.
- The first combined attempt hit local API timeouts. A subsequent run exposed navigation timing in the test harness; waits were corrected. The final combined run passed without increasing production API timeouts to hide failures.
- New artifacts: [intake result](.cache/verification/intake-result.json), [SMS mobile](.cache/verification/intake-sms-mobile.png), [voice mobile](.cache/verification/intake-voice-mobile.png), [Command source](.cache/verification/intake-command-source.png).

See [INTAKE_HANDOVER.md](INTAKE_HANDOVER.md) for exact modified/created files, commands and deployment limitations. No real telecom provider/number was connected, and no cloud deployment was performed.

## 8 September 2026: original completion baseline

Verified on 8 September 2026 in:
`C:\Users\DELL\OneDrive\Desktop\AEGIS-MAIN`

Result: **working local demo**, with external map/routing connectivity limits described below. No deployment or external account changes were performed.

## Environment

- Windows / PowerShell
- Node 24.19.0
- Python 3.12.10 in `backend/.venv`
- React / React DOM 19.2.8; React Router 7.18.3
- Vite 8.2.2; TypeScript 6.0.3; Oxlint 1.81.0
- MapLibre GL 6.7.0
- FastAPI 0.141.1; Pydantic 2.13.5; Uvicorn 0.52.4; HTTPX 0.28.1
- WebSockets 17.1 for Chrome automation

## Commands and results

All commands ran from the project root. npm, pip and temporary directories were redirected to `.cache`.

| Exact command or check | Result |
| --- | --- |
| `npm.cmd --prefix frontend install --package-lock-only --offline --ignore-scripts --no-audit --no-fund` | PASS: dependency lock updated without a registry download |
| `npm.cmd --prefix frontend prune --offline --ignore-scripts --no-audit --no-fund` | PASS: 325 unused packages removed |
| `npm.cmd --prefix frontend ls --depth=0` | PASS after pruning: required dependency tree, no extraneous packages |
| `.\backend\.venv\Scripts\python.exe -B -m pip install --no-index --no-deps --disable-pip-version-check -r backend/requirements-dev.txt` | PASS: all specified dependencies already satisfied locally |
| `.\backend\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -v` | PASS: 20 tests |
| `npm.cmd --prefix frontend run build` | PASS: TypeScript check and production build, including after dependency pruning |
| `npm.cmd --prefix frontend run lint` | PASS: zero findings |
| `npm.cmd --prefix frontend test` | PASS: 16 routing/movement assertions |
| `.\backend\.venv\Scripts\python.exe -B scripts/browser_smoke.py` | PASS: full browser workflow |
| `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Aegis.ps1 -Component Backend -FreshDemo` | PASS: FastAPI starts on 8001 with a new empty database |
| `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Aegis.ps1 -Component Frontend` | PASS: Vite starts on 5173 |
| GET `http://127.0.0.1:5173/api/health` and `/api/reports` | PASS: frontend proxy reaches healthy backend and empty demo database |
| Python AST parse of backend source; PowerShell parser check of launcher | PASS |

Production output: initial application JavaScript about 332 kB (100 kB gzip), separate operational-map component about 10 kB, and a MapLibre vendor chunk about 987 kB (259 kB gzip). Vite retains a warning about the vendor chunk exceeding 500 kB. Build success is not a claim of a formal performance benchmark.

## Backend coverage

The 20 tests cover request validation, missing IDs, reset disabled by default, severity factors, hospital capability/capacity/hazard constraints, resource shortages, no assignment sharing between separate incidents, concurrent dispatch, duplicate observation aggregation, repeated-evidence handling, status transitions, idempotent departure, persistence, reassignment/audit, zero/distant hazard exposure, carrying capacity, relocation conservation, closed shelters, What-If isolation, projected risk and spare staging.

Legacy-analysis upgrade is tested against an isolated old-format envelope: report observations, assignments and status survive; the original calculation is retained in audit; a second upgrade does nothing.

## Browser coverage

Chrome automation used isolated servers on 8002/5174, a new database and a project-local profile. It verified:

1. Command standby without an automatically selected incident.
2. Citizen submission, persisted receipt and Track My Report.
3. Exact incident selection, stage presentation and map overlays.
4. Acknowledgment, dispatch and route/fallback status.
5. Moving markers with unchanged marker and canvas object identity.
6. Arrival synchronized to the backend.
7. Hospital/shelter What-If recalculation with saved operation unchanged.
8. Prediction, spare staging, shelter closure, relocation and audit tabs.
9. Mobile responder layout, zero ETA on arrival and persisted completion.
10. Mobile citizen layout without horizontal overflow.
11. Missing-report error without choosing an unrelated incident.
12. Legacy URLs and refresh persistence.

Observed: **zero uncaught runtime exceptions, zero console errors/warnings, and zero backend/frontend server tracebacks**. Browser network errors occurred for unreachable external services and the deliberately missing report.

Recorded smoke report: `AEGIS-20260908075739-1C382E`.
It exists only in its verification database, not the normal user database.

Artifacts:

- [Browser result](.cache/verification/browser-result.json)
- [Browser events](.cache/verification/browser-events.json)
- [Moving units](.cache/verification/moving-units.png)
- [What-If comparison](.cache/verification/what-if.png)
- [Responder mobile](.cache/verification/responder-mobile.png)
- [Citizen mobile](.cache/verification/citizen-mobile.png)
- [Backend log](.cache/verification/server-0.log)
- [Frontend log](.cache/verification/server-1.log)

These artifacts are ignored local verification files, not committed product assets.

## What was not verified

- Fresh internet-based dependency installation: registry requests were unavailable. Existing installed dependencies, local offline reconciliation and builds were verified.
- Successful live OSRM responses and OSM street tiles: unavailable in this environment. The browser exercised the clearly labeled straight-line fallback. Deterministic route tests separately verified safer-alternative selection using returned-route-shaped geometry.
- Real GPS permission, browser speech-provider integration, government/telecom feeds, real hospital capacity or vehicle telemetry.
- Public deployment, authentication, scientifically calibrated prediction or a multi-device telemetry system.
- A formal memory/performance benchmark. Browser checks established stable map/marker identity during the demonstration, rather than proving absence of every possible stutter.

## Saved data and filesystem boundary

Verification databases, profiles, logs, dependency caches and generated build files stayed inside AEGIS-MAIN. The normal `data/aegis.db` was inspected read-only and retained its original **1 report, 3 assignments and 21 audit events** throughout verification.

Normal backend startup will apply additive schema migration and preserve old analysis envelopes in audit when upgrading them. The fresh-demo launcher avoids that database entirely.
