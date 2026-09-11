# Call, SMS and local NLP upgrade

The September 10 multilingual voice batch extends this implementation. See [VOICE_HANDOVER.md](VOICE_HANDOVER.md) for the current MediaRecorder/Sarvam/NVIDIA flow, explicit CALL analysis, confidence, persisted provider metadata and verification. This document records the original local-only intake baseline.

Updated 9 September 2026. All implementation and verification writes stayed inside AEGIS-MAIN.

## What changed for citizens

The existing online form remains available at /report with all its fields. A shared selector now links ONLINE REPORT, TEXT / SMS and VOICE / CALL. Existing /sms and /call URLs are retained.

Text and voice use the same review flow:

1. Type a message, or start browser speech recognition.
2. Stop recording and review the transcript. Text is parsed after a short typing pause; speech is parsed after recording stops.
3. The backend returns an interpretation, missing-information questions and extraction confidence.
4. Correct the type, place, counts, vulnerable groups, flags or estimated intensity through EDIT DETAILS.
5. Confirm GPS or provide manual incident coordinates.
6. Select SEND EMERGENCY REPORT.
7. Follow the saved receipt through tracking into the existing Command Center.

Nothing submits automatically. No NLP output directly dispatches a unit.

## Backend design

POST /intake/parse accepts source CALL or SMS and text, plus optional latitude, longitude and gps_verified. It returns incident_type, location, nullable people_affected/injured/trapped, vulnerable_groups, nullable spreading/structural_damage, estimated hazard_intensity, original description, confidence factors, missing_fields, questions and warnings.

The parser is in backend/intake_nlp.py. It recognizes English emergency synonyms, numeric digits and number words, useful location phrases, casualty counts, vulnerable groups and urgency clues. It handles common negation, ambiguous incident types, invalid/ranged counts and missing details conservatively. Its interface accepts another validated parser implementation later. No LLM, model download or API key is required.

Extraction confidence is a transparent completeness score: incident 30 points, place 20, GPS 15, affected count 15, and up to 15 for useful details. It is separate from backend incident evidence quality and severity. Corrections do not pretend to improve the original text's extraction score.

Unknown values stay null during review. The existing report API still needs numeric counts and boolean flags. Submission uses zero for unstated injured/trapped, the known injured/trapped minimum for an unknown total, and false for unstated flags. Those are analysis defaults, not assertions that nobody is hurt or danger is absent. The intake record retains unknown_fields and nullable reviewed values so Command can distinguish them.

The existing POST /reports remains the only citizen submission path. It recomputes extraction on the backend from raw_content, saves source SMS/CALL, and records the reviewed observations and corrected fields. A nullable intake_json column is added to reports without removing data. APP and legacy reports remain compatible.

Fusion, severity, resource/hospital/risk/relocation engines, What-If and dispatch are unchanged in authority. The original shared assignment system still handles dispatch/reassignment. INTAKE_REVIEWED audit events explain the source and reviewed fields.

Command's source details show the original transcript/message, original-text extraction confidence, reviewed observation, unknown fields, corrections and fusion ID. These are per-report observations; operational panels continue to use the fused estimate.

## Speech, location and errors

Browser SpeechRecognition or webkitSpeechRecognition is used when available, with en-IN recognition language. START, STOP, RETRY and EDIT TRANSCRIPT are provided. Retry starts a new transcript. Recognition stops and listeners are cleared on leaving the page. Submission is disabled while listening.

Microphone denial, no speech, unavailable microphone, speech network failure and unsupported browsers have readable messages and a typed-transcript fallback. Browser recognition may use the browser vendor's online service. No audio recording is uploaded or stored by AEGIS; the reviewed transcript is submitted.

Voice/text modes ask for device GPS and explain why. Denied/unavailable GPS leaves coordinates empty and allows manual entry. Empty inputs never become latitude 0 / longitude 0. Editing either coordinate clears the GPS-verified flag. Late GPS callbacks cannot overwrite manual edits.

Parsing waits 650 ms after typing, cancels obsolete requests and allows up to 60 seconds for a backend cold start. After eight seconds it explains that the backend may be waking. Text remains visible through failures, with an explicit retry. The ordinary shared report submission retains its existing timeout; failed delivery produces no success receipt and does not erase the message.

## Real, rule-based and simulated

| Category | This upgrade |
| --- | --- |
| Real application functions | Input/review, browser capability calls, HTTP APIs, SQLite, source/transcript storage, tracking, fusion and Command integration |
| Rule-based | English NLP extraction, estimated intensity and extraction confidence; existing deterministic AEGIS engines |
| Existing simulations | Predicted hazards, vehicle movement, blocked roads and demo infrastructure remain explicitly labeled |
| Test simulations | Speech events and GPS fixes/permission states in automated browser checks |
| Not connected | Real telephone number, SMS gateway, telecom provider, paid LLM |

The telecom/provider.py boundary describes verified inbound events and a provider signature/normalization interface. It can prepare an event for review; it cannot save or dispatch. No live webhook or provider-specific verification is implemented. GET /intake/capabilities reports PROVIDER_READY_NOT_CONFIGURED and a null telephone number.

## Telecom investigation

Software alone does not provision a telephone number. Twilio trials require account setup and verified recipients; test credentials simulate provider actions without connecting real numbers. See [Twilio trials](https://www.twilio.com/docs/usage/trials) and [test credentials](https://www.twilio.com/docs/iam/test-credentials).

Exotel's trial setup also has account/verification constraints; its documentation describes restricted trial calling and SMS testing. See [Exotel trial setup](https://docs.exotel.com/business-phone-system/create-a-trial-account).

Neither is a ready, unconfigured emergency number for this prototype. No account was created, number provisioned, payment made or telecom message sent. A future integration needs provider onboarding, authenticated webhooks, replay protection, transcription where required, location capture and review before shared report submission.

## Run locally

Restart an already running backend to load the new endpoint and additive schema migration. In two PowerShell terminals at the project root:

Backend:

```powershell
cd "C:\Users\DELL\OneDrive\Desktop\AEGIS-MAIN"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Aegis.ps1 -Component Backend
```

Frontend:

```powershell
cd "C:\Users\DELL\OneDrive\Desktop\AEGIS-MAIN"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Aegis.ps1 -Component Frontend
```

For an isolated demonstration, add -FreshDemo to the backend command. It creates a new database inside the project. No new packages or environment variables are required for this upgrade.

## Try SMS

Open http://127.0.0.1:5173/report and select TEXT / SMS. Enter:

> Flood near Anna Nagar bridge. Water is increasing quickly. Around thirty people are trapped and elderly people are present.

Expected: Flood, Anna Nagar bridge, 30 affected/trapped, Elderly, spreading Yes, injuries/structural damage Unknown. The affected count is explicitly labeled as coming from the trapped group.

Review/correct, allow GPS or enter actual incident coordinates, then send. Track the report and expand SOURCE: SMS in Command to inspect its original text and interpretation.

## Try voice

Select VOICE / CALL, allow microphone/GPS, and select START SPEAKING:

> There is a fire near the college hostel. The fire is spreading. Around twenty people are inside and two people are injured.

Press STOP. Expected: Fire, college hostel, 20 affected, 2 injured, spreading Yes. Edit mistakes before sending. Follow tracking into Command and expand SOURCE: CALL.

If speech is unsupported or blocked, type/paste the transcript. If using manual demo coordinates such as 13.13, 80.22, recognize that they are demo coordinates, not a detected location.

## Vercel and Render

VITE_API_BASE_URL support is preserved. No localhost URL was added to the intake implementation.

For Vercel, use frontend as the project root, npm run build, and dist output. Set VITE_API_BASE_URL to the actual HTTPS Render origin without a trailing /api unless your own proxy requires one. Redeploy after changing build-time variables. frontend/vercel.json supplies SPA deep-link rewrites for /sms, /call, tracking and the other routes. See [Vercel Vite documentation](https://vercel.com/docs/frameworks/frontend/vite).

For Render with backend as service root: install requirements.txt and start uvicorn main:app --host 0.0.0.0 --port $PORT. With repository root as service root: install backend/requirements.txt and add --app-dir backend. Use Python 3.12, keep data/*.json in the deployment, and configure AEGIS_CORS_ORIGINS with the exact HTTPS Vercel origin. See [Render FastAPI documentation](https://render.com/docs/deploy-fastapi).

AEGIS_DB_PATH must remain inside the project tree, as before. Ensure SQLite storage persists across your chosen hosting lifecycle; ephemeral storage is unsuitable for retaining real reports. HTTPS is needed for browser permissions away from localhost. No cloud deployment or hosted microphone verification was performed.

## Verification

Commands:

```powershell
.\backend\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -v
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend test
.\backend\.venv\Scripts\python.exe -B scripts/browser_intake_smoke.py
```

The browser command includes the existing full demo regression and new intake checks. For intake-only debugging, add --intake-only. It reuses the original Chrome harness, creates a separate database, and writes artifacts under .cache/verification.

Current verified results: 34 backend tests; 16 existing routing assertions and 12 intake API assertions. Intake-only browser checks passed SMS/CALL review and persistence, Command text/source, tracking, GPS success/denial/manual entry, unknowns, correction preservation, failed parsing/submission, cold starts, stale requests, unsupported speech, speech errors/retry and recorder cleanup.

Speech recognition is tested with a browser-event double, not a real microphone/provider. GPS uses Chrome emulation and permission controls. The local and production API base URL cases are tested without external HTTP calls. A local production build is not a cloud deployment.

Final combined-suite/build results are recorded in VERIFICATION.md. Browser artifacts include intake-result.json, intake-sms-mobile.png, intake-voice-mobile.png and intake-command-source.png. No verification ran against the user's normal database.

## Limitations

The local parser targets English and cannot reliably interpret every accent, dialect, mixed language, negation, relative location or complex multi-incident narrative. Review is required. Named places are not geocoded; a valid GPS fix/manual coordinates are necessary. Estimated hazard intensity is not a sensor measurement. Microphone availability and speech recognition depend on browser support, permission and sometimes connectivity. No real telecom number or paid model is configured.

Existing prototype limitations still apply: no role authentication for public operations, demo infrastructure, no real telemetry and no shared bed/shelter reservations.

## Exact file inventory for this upgrade

Modified:

- backend/main.py
- backend/models.py
- backend/db.py
- backend/operations.py
- frontend/src/App.tsx
- frontend/src/App.css
- frontend/src/api.ts
- frontend/src/IntakeChannels.tsx
- frontend/package.json
- scripts/browser_smoke.py
- README.md
- ARCHITECTURE.md
- PROJECT_HANDOVER.md
- VERIFICATION.md

Created:

- backend/intake_nlp.py
- backend/telecom/provider.py
- backend/tests/test_intake.py
- frontend/src/IntakeMethodSelector.tsx
- frontend/src/IntakeReportDetails.tsx
- frontend/src/useVoiceIntake.ts
- frontend/src/useIntakeLocation.ts
- frontend/vercel.json
- scripts/test-intake-api.mjs
- scripts/browser_intake_smoke.py
- INTAKE_HANDOVER.md

Generated files are confined to ignored project-local build/cache/verification directories. No new dependency was installed.
