# AEGIS project handover

The 9 September voice/text upgrade adds local backend NLP, review/correction, GPS permission handling and original-message inspection in Command. Read [INTAKE_HANDOVER.md](INTAKE_HANDOVER.md) for its schemas, confidence/default rules, tests and deployment instructions. The original engines and dispatch authority remain in place.

## What happens internally after Submit?

The citizen supplies type, location, coordinates, people, injuries, trapped people and hazard clues. The form sends a structured report to FastAPI. Pydantic rejects invalid coordinates, non-finite values, negative counts, or injured/trapped counts greater than the total.

The backend saves the original observation in SQLite, groups nearby related reports, and calculates one shared incident estimate. Engines score severity/evidence, determine required capabilities, rank available units, find suitable hospitals, identify population exposure, project a future footprint, allocate safe shelter capacity and recommend spare-unit staging.

The receipt has a persistent ID. Track My Report selects that exact report in Command. The operator reviews, acknowledges and dispatches. Status updates are stored and shared with Responder. The map obtains OSRM driving geometry, or a labeled estimated fallback, and moves unit markers when the demonstration starts.

## Engines and formulas

### Severity

`severity_engine.py` adds visible contributions, capped at 100:

| Factor | Points |
| --- | --- |
| Baseline | 10 |
| Flood/fire/landslide | 15 |
| Affected people | +10 at 10, another +8 at 50, another +7 at 100 |
| Intensity | 20 multiplied by intensity (0-1) |
| Injured | 2 each, capped at 10 |
| Trapped | 3 each, capped at 10 |
| Vulnerable groups | 2 per group, capped at 5 |
| Spreading / structural damage | 8 / 7 |

LOW is below 40, MODERATE starts at 40, HIGH at 60 and CRITICAL at 80. The demo fill gives 79/HIGH. This is an explainable prototype rule, not a clinical scale.

### Confidence and priority

`confidence_engine.py` measures evidence quality, not probability. It starts at 35; adds up to 24 for distinct reports, 12 for source diversity, 14 for reported browser GPS and 8 for a description of at least 20 characters; and caps at 95. Matching contact, normalized description and rounded coordinates count as one evidence item. Different content does not prove independent identity. GPS metadata is client-supplied.

Priority = round(0.85 * severity + min(10, affected / 10) + min(5, trapped)), capped at 100. Low evidence does not reduce the urgency of a dangerous report.

### Resource allocation

`resource_engine.py` calculates incident-specific unit requirements. Floods require boats, rescue teams, ambulance support and police. Larger populations increase capped demand. Unit counts do not assert that one trip can transport everyone.

Candidates need the correct capability, AVAILABLE status, no active assignment to another incident, and distance within 75 km. Estimated travel is 2.4 min/km, increased by 50% for a blocked-road What-If, plus requested response delay.

Candidate cost adds six points for an exposed non-boat origin and five for using a staging reserve below critical severity, then subtracts a bounded capacity benefit. Lowest cost wins per capability. Outputs include reasons, ETA basis, capacity, spares and shortages. Dispatch checks current occupancy again in its transaction.

OSRM times are calculated later in the frontend and do not feed backend ranking. Global multi-incident optimization is not implemented.

### Hospital selection

`hospital_engine.py` requires demo beds, relevant burn/trauma capability, a destination outside the future footprint and range within 75 km. Ranking considers estimated travel, treatment shortfall, beds and ICU capability. A hospital can have an explicit shortfall when no fully sufficient one exists. No suitable hospital returns an empty result. Beds are not booked.

### Current habitation risk

`risk_engine.py` uses intensity times a maximum radius: flood 3.5 km, landslide 2 km, fire 1.2 km, accident 0.2 km. Zero intensity means zero exposure.

For distance d and radius r:

- exposure = max(0, 1 - (d/r)^2)
- risk = 100 * intensity * exposure * (0.5 + 0.25 * susceptibility + 0.15 * historical score + 0.1 * vulnerability)
- estimated affected residents = catalogue population * intensity * exposure

Risk bands: RED at 75, ORANGE at 55, YELLOW at 25, otherwise GREEN. RED/ORANGE populations drive evacuation planning. Catalogue vulnerable-group counts describe residents and must not be added again to the total. Distant incidents produce no spurious local evacuation and flag dataset coverage.

### Prediction and spare staging

`prediction_engine.py` expands flood/fire/landslide footprints when intensity is positive. At 30 minutes, radius growth is 60% when spreading and 25% otherwise; growth scales with horizon. Future intensity increases by 0.2 times growth, capped at one. The risk engine recalculates future habitation exposure and unit demand.

This projected footprint excludes future-exposed hospitals and shelters. For up to two rising-risk habitations scoring at least 55, compatible spare units are recommended to points 0.5 km outside the future footprint, in the threatened area's direction. Each recommendation uses a different spare unit and an estimated ETA.

This is radial simulation without weather, terrain, wind or official forecasts. Staging points are not verified for road access or land suitability. Recommendations create no dispatch.

### Carrying capacity and relocation

`capacity_engine.py` takes the minimum of space, water, food, sanitation and medical capacity. Available space is max(0, that minimum minus occupancy). It reports the limiting factor.

`relocation_engine.py` excludes unsafe, closed, fully occupied, distant and future-exposed destinations. It applies a What-If capacity factor before subtracting occupancy, then fills suitable shelters by distance. Allocated plus unallocated people always equals the requirement. No shelter receives more than its available capacity.

Citizen observations and modeled habitation exposure are separately labeled populations. In the demo, 18 reported people and 1,422 residents requiring relocation describe different scopes. Shelter plans are per incident; they do not reserve catalogue capacity across simultaneous incidents.

### What-If

Population, intensity, unit availability, road delay and hospital/shelter capacity controls call the actual `/aegis-analyse` pipeline. The predictive panel can close a specific shelter. The API also accepts response delay and forecast horizon. Changed controls invalidate the previous comparison; no live report, assignment or occupancy is altered.

The map road-block demonstration is separate: a 120 m exclusion area around the primary route midpoint is compared with returned OSRM alternatives. A less exposed returned route is selected if available. No road detour is invented. The scenario is fixed after departure and shared only within the same browser.

## Movement, responder and persistence

`routing.ts` precomputes cumulative segment lengths, then uses binary search to interpolate by distance. A single animation loop moves existing markers smoothly; ETA updates more slowly. Demo travel is compressed to 18-55 seconds.

Persisted `departed_at` prevents refresh from restarting movement. ISSUE freezes progress; ON_SCENE has zero remaining ETA. Open maps synchronize arrival to FastAPI. Responder controls support acceptance, departure, arrival, completion and issue reporting. All active units must complete before the fused incident resolves. Audit events record progress and replacements.

## Real functions and simulation boundaries

| Working feature | Boundary |
| --- | --- |
| Forms, APIs, SQLite, dispatch, shared statuses and audit | Local prototype without authentication |
| Browser GPS | Requires permission and supported secure context; manual/demo coordinates remain available |
| Fusion, severity, evidence, allocation, capacity, What-If | Deterministic rules, not trained AI or validated probabilities |
| OSRM driving routes | External service; failure uses straight-line estimation |
| OpenStreetMap tiles | External; no offline street-tile package |
| SMS/text and call transcript intake | Manual/browser input, no telecom dispatch integration |
| Optional browser speech recognition | Browser/provider dependent, not required for the demo |
| Forecast, blocked roads, moving vehicles | Simulation without official feeds or live telemetry |
| Resources, hospitals and shelters | Static demo catalogues, no real bookings or dispatch |

Image evidence ingestion and a configured PWA were absent from the active project and are not claimed as integrations.

## Maintain and extend it

[ARCHITECTURE.md](ARCHITECTURE.md) explains files, roles and API flow. [README.md](README.md) provides exact frontend/backend commands and every configuration variable. [DEMO_GUIDE.md](DEMO_GUIDE.md) gives a faculty presentation.

Keep authoritative calculations in backend engines. When changing them, test no double-booking, duplicate-population summation, negative capacity, unsafe destinations or What-If mutation. Catalogue loaders and the routing adapter are the boundaries for real feeds.

Verification used separate databases. On first normal startup, additive schema migration and a one-time legacy-analysis refresh preserve observations/assignments and keep previous calculations in audit metadata. Back up the normal database before future structural changes.

Remaining work for operational deployment: authentication and roles, real infrastructure/telemetry adapters, incident review/splitting, shared bed/shelter reservations, validated forecasting and staging accessibility checks. The isolated MapLibre vendor chunk still triggers a production size warning.
