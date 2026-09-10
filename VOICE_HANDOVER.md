# AEGIS multilingual voice handover

This batch extends the existing `/call` intake. Reporter, SMS, Tracking, Command, Responder and the deterministic operational engines remain in place. Speech and NLP never dispatch resources or submit reports automatically.

## Run locally

Open two PowerShell terminals. In each:

```powershell
Set-Location 'C:\Users\DELL\OneDrive\Desktop\AEGIS-MAIN'
```

Terminal 1:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Aegis.ps1 -Component Backend
```

Terminal 2:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Aegis.ps1 -Component Frontend
```

Use these URLs:

| Page | URL |
| --- | --- |
| Voice | http://127.0.0.1:5173/call |
| Reporter | http://127.0.0.1:5173/report |
| SMS | http://127.0.0.1:5173/sms |
| Command | http://127.0.0.1:5173/command |
| Responder | http://127.0.0.1:5173/responder |
| API schemas | http://127.0.0.1:8001/docs |

The normal backend uses saved `data/aegis.db`. Add `-FreshDemo` to the backend command to use a new isolated demo database. Stop each server with Ctrl+C. Restart an already-running backend to load the new code and configuration.

## Dependencies and configuration

Added `python-dotenv==1.2.3` to backend requirements; that version was already installed in this workspace's virtual environment. No frontend dependencies, provider SDKs, audio converters or global packages were added.

`provider_config.py` loads only `backend/.env`, without overriding shell values. `SARVAM_API_KEY` and `NVIDIA_API_KEY` stay in that file or backend environment variables. No frontend provider authentication exists. `.env.example` contains empty placeholders. `.env` is ignored and must remain untracked. Existing Vite `/api` proxy and `VITE_API_BASE_URL` behavior are retained.

## Speech architecture

`useRecordedVoice.ts` requests microphone audio with echo cancellation, noise suppression and automatic gain control. Browser support determines whether those constraints take effect. This is browser preprocessing, not Krisp.

The hook records actual WebM/Opus audio with MediaRecorder, shows a timer, stops at 25 seconds, releases microphone tracks, then uploads the Blob to `POST /voice/transcribe`. The endpoint accepts raw `audio/webm` content (not a multipart form), rejects empty uploads and caps them at 5 MiB. Audio stays in memory and is not saved to disk or the database.

`speech/provider.py` defines the provider contract and validated response. `speech/sarvam.py` sends multipart audio from the backend to Sarvam `/speech-to-text`, using `saaras:v3`, `language_code=unknown`, and `mode=codemix`. These settings support automatic detection and preserve English words alongside Indic script. See the [official Sarvam REST reference](https://docs.sarvam.ai/api-reference/speech-to-text/transcribe).

The response includes provider, model, dominant detected language, transcript, nullable confidence and an opaque server result ID. Sarvam's `language_probability` is not transcript confidence; it is deliberately not reused as such. Transcript confidence remains null with the current provider response.

If Sarvam fails, the UI explicitly says: “Advanced multilingual transcription unavailable. Using browser speech recognition fallback.” Press START SPEAKING again to repeat the message using the existing browser recognizer; RETRY attempts primary recording again. This new user gesture also handles browsers that require activation to start speech recognition. Browsers without WebM/Opus recording use browser recognition directly. If neither capability works, manual transcript editing remains available.

Browser fallback uses the browser locale, not hard-coded en-IN or claimed automatic detection. Its language hint and transcript are client reported; detected language stays unknown. Cleanup aborts uploads/recognition and releases recording tracks when leaving the page.

## Advanced NLP and fallback

`nlp/provider.py` defines a strict Pydantic schema. `nlp/nvidia.py` calls NVIDIA's hosted chat-completions API with **`google/gemma-4-31b-it`**, low temperature and thinking disabled for bounded extraction latency. No tools or dispatch functions are supplied.

This instruction-tuned model was selected because it supports multilingual instructions and structured output, with broad language coverage suitable for testing Indian and code-mixed text. Its exact ID was present in the authenticated model catalog for the current key on September 10, 2026. See [NVIDIA's model page](https://build.nvidia.com/google/gemma-4-31b-it), [Google's model card](https://ai.google.dev/gemma/docs/core/model_card_4), and [NVIDIA's request parameters](https://docs.api.nvidia.com/nim/reference/google-gemma-4-31b-it-infer).

**Live inference remains unverified:** bounded synthetic extraction and a final 32-token access request timed out. Listing access is confirmed; successful live completion, real-world language quality and latency are not. Automated tests use mocked HTTP and incur no provider credits. The app falls back to local rules on these failures.

The provider requests one JSON object, validates every required field, rejects extra fields, invalid types, counts, ranges and nonfinite scores, and retries malformed output once. It never accepts arbitrary prose. This uses server validation rather than assuming the hosted endpoint implements strict JSON-schema response mode. HTTP/auth/rate-limit failures fall back immediately; retries share an overall 70-second budget. Normal AEGIS requests retain their 12-second timeout; browser transcription uses 60 seconds and NLP uses 90 seconds. Sarvam's backend deadline is 45 seconds; NVIDIA requests use a 45-second individual timeout inside the overall budget.

`nlp/router.py` verifies that populated facts have supporting verbatim transcript snippets, clears unsupported facts, flags conflicting counts, and returns `ADVANCED_NLP` with the actual provider/model. Source text is treated as untrusted data, never instructions. Model evidence matching reduces unsupported extraction but does not prove interpretation is correct; citizen review remains required.

On missing credentials, invalid output, timeout or provider failure, the existing `backend/intake_nlp.py` parser runs. The response and UI say `LOCAL_RULE_BASED` and warn that those rules are English-focused. It cannot promise multilingual understanding.

## Confidence, clarification and review

Unknown counts/flags remain null in the extraction and reviewed intake record. A fire near a hostel does not establish injuries, trapped people, total population or damage. Affected subgroups do not automatically establish an overall total in the advanced parser.

Advanced confidence values are optional model self-assessments, explicitly uncalibrated, never validated probabilities or severity scores. Unknown or unrated fields display “Unrated.” Local overall confidence remains the existing heuristic completeness score; local field confidence is null rather than invented numbers.

Missing critical fields or model scores below 0.7 generate short questions for incident type, location, affected people, injured, trapped and spreading. These appear with the review, with detailed field scores expandable. The threshold is a review prompt, not a calibrated risk threshold. GPS still comes from device/manual input, never the LLM.

CALL proceeds through START SPEAKING → STOP → transcript → ANALYZE EMERGENCY → structured review/corrections → SEND EMERGENCY REPORT. No analysis or report is automatically submitted after speech. GPS changes after CALL analysis do not make another paid NLP request. SMS retains debounced text analysis.

Existing operational defaults remain explicit: unstated injuries/trapped use zero for calculations, an unknown total uses the known victim minimum, unknown flags use false, and missing hazard magnitude uses 0.5. The intake record retains the unknowns so those defaults are not mistaken for observed safety.

## Persistence and Command integration

The database change adds only `intake_previews`. Opaque IDs reference server-owned STT and NLP snapshots, surviving a backend restart. Previews expire after 24 hours and expired rows are pruned on subsequent preview writes; this does not delete reports. Re-analyze after expiration. Raw audio is not stored. A preview creates no report, assignment or dispatch.

Report confirmation sends the NLP result ID alongside the existing reviewed fields to `POST /reports`. The server verifies source and exact analyzed text, then copies the snapshot into the existing per-report `intake_json`; it does not re-call NVIDIA. APP and legacy SMS/CALL submissions remain compatible, with local metadata reconstruction when no preview ID is supplied.

Stored metadata includes speech provider/model, detected language, original transcript, NLP provider/model/method, field confidence, missing fields, original structured extraction, reviewed observations and citizen corrections (including transcript changes). Browser language hints are distinguished from detected language. Confirmed snapshots persist independently of preview expiry.

The existing report/fusion/severity/resource path then runs. The receipt links to Tracking and the specific Command incident. Command's expandable source area shows original speech, providers, structured interpretation, uncertain fields, corrections and fusion ID. Primary operational panels continue to use the fused incident estimate.

## Verification

Commands from the root:

```powershell
.\backend\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -v
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend test
.\backend\.venv\Scripts\python.exe -B scripts/browser_intake_smoke.py --intake-only
.\backend\.venv\Scripts\python.exe -B scripts/browser_voice_smoke.py
```

For a focused voice rerun, append `--voice-only`; run `scripts/browser_smoke.py` separately for the operational regression. Browser sessions use fresh isolated profiles to avoid carrying dev-server module caches across runs.

Use the cache environment settings in README for dependency installation and npm commands on a fresh checkout. Verification scripts use project-local temporary files, Chrome profiles and isolated SQLite databases; real provider keys are disabled in their servers. `browser_voice_server.py` is strictly a test entry point guarded by an isolated database path, never the normal launcher.

Passing results: all 47 backend tests (the existing 34 plus 13 provider/provenance tests); 16 routing and 22 intake/voice API assertions; frontend compilation/build/lint (no lint warnings); Python compilation of 27 backend files; all seven existing intake browser checks; and all five focused synthetic microphone voice checks with zero uncaught browser exceptions.

The full operational browser flow passed once earlier in the session, but subsequent reruns were not consistently green: development runs stalled loading the existing MapLibre module, and production-preview runs reached the map but timed out around acknowledgement/dispatch refresh requests. Request tracing and isolated profiles were added; this remains an unresolved browser verification limitation, not a claimed clean full-suite pass. Operational backend invariants pass. Recheck the full Command/Responder flow locally before merging. `scripts/browser_smoke.py --production` tests the built app; public tile/OSRM requests are blocked in the harness to exercise documented offline fallbacks without depending on those services.

The existing large MapLibre vendor-chunk build warning is unchanged. Generated artifacts stay under `.cache/verification` and are not committed.

## Real microphone/API acceptance checklist

Live Sarvam transcription, NVIDIA latency/quality, noisy microphones and browser/device support still need real testing. In `/call`, speak English, Telugu, Tamil, Hindi and each language mixed with English. Check names, counts, negations, unknowns and detected dominant language before submitting.

Try the supplied examples:

- “Hostel daggara fire start ayyindi, around twenty students inside unnaru.”
- “Bridge pakkam water romba increase aaguthu, thirty people stuck.”
- “Bridge ke paas paani bahut badh gaya hai, twenty log phase hue hain.”
- “There is a fire near the hostel.” Counts and damage should remain unknown.

Also try denied microphone permission, no speech, STOP/RETRY, edit-before-analysis, corrections, unavailable providers and leaving the page during recording. Confirm the report's source details in Command. Model language quality must be checked by speakers of each language; mocked fixtures are not evidence of recognition accuracy.

## Files

Created:

- `backend/provider_config.py`, `backend/intake_records.py`
- `backend/speech/__init__.py`, `provider.py`, `sarvam.py`
- `backend/nlp/__init__.py`, `provider.py`, `nvidia.py`, `router.py`
- `backend/tests/test_voice.py`
- `frontend/src/useRecordedVoice.ts`
- `scripts/browser_voice_server.py`, `scripts/browser_voice_smoke.py`
- `VOICE_HANDOVER.md`

Modified:

- `backend/.env.example`, `backend/requirements.txt`
- `backend/main.py`, `db.py`, `models.py`, `operations.py`, `intake_nlp.py`
- `backend/tests/test_intake.py`
- `frontend/src/api.ts`, `IntakeChannels.tsx`, `IntakeReportDetails.tsx`, `useVoiceIntake.ts`
- `scripts/browser_smoke.py`, `browser_intake_smoke.py`, `test-intake-api.mjs`
- `README.md`, `INTAKE_HANDOVER.md`

The user's `.vscode` settings are outside this change. No keys, local databases, audio recordings, caches or screenshots belong in the commit. The dedicated branch is `codex/aegis-multilingual-advanced-voice`, targeting `main` via a pull request. Do not merge automatically.
