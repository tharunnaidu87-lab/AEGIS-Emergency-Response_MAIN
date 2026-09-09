# AEGIS demo guide

Allow about five minutes. Use a laptop for Command and optionally browser mobile emulation for Responder.

## Start with an empty operation

Use the two launcher commands in [README.md](README.md), adding **-FreshDemo** for the backend. This creates a new database without clearing saved work.

Open http://127.0.0.1:5173/command first. Say: "Infrastructure is local demo data. No active disaster appears until somebody submits a report."

## Submit and track

1. Open http://127.0.0.1:5173/report.
2. Select **FILL FLOOD DEMO SCENARIO**.
3. Review Riverbank Village, coordinates 13.13 / 80.22, 18 affected, 3 injured, 4 trapped, intensity 0.8, children/elderly and spreading water.
4. Submit, then select **TRACK MY REPORT** on the receipt.

Say: "The report ID is persisted. All following views use this incident. The backend validates and calculates before returning this receipt."

Command presents the pipeline in about a second. Explain that it reveals completed backend stages with measured timings, rather than claiming a live streamed calculation.

## Explain and dispatch

5. Show **79 / HIGH** severity, **43** evidence quality and **73** priority for the fresh demo. Expand the contributing factors.
6. Show boat, rescue team, ambulance and police recommendations, reasons and any shortages.
7. Acknowledge the report, then dispatch.
8. Wait for route calculation. Select **SIMULATE BLOCKED ROAD** before departure to inspect an OSRM alternative when available.
9. Select **START DEMO MOVEMENT**. Watch units travel for 18-55 seconds, select individual units and show remaining ETA. Arrival becomes ON_SCENE.

Say: "Selection considers capability, availability, estimated travel, exposure and capacity. Positions are simulated; road geometry comes from OSRM when reachable."

If routing is unavailable, point out **ESTIMATED STRAIGHT-LINE FALLBACK**. A closure cannot be assessed against a straight line. Do not call it a safe road route. If tiles fail, operational layers remain on the dark background.

## Connect prediction to decisions

10. Point to current danger and the dashed violet future footprint. Use **FIT OPERATION** as needed.
11. Show hospital, shelter and **P** staging markers.
12. Open **PREDICTIVE**, then **INTELLIGENCE** to show projected population and spare-resource staging.

Say: "At these inputs, radius expands from 2.80 to 4.48 km over 30 minutes. The projected footprint excludes unsafe destinations and drives staging recommendations. This is a rule-based scenario without rainfall or government forecasts."

Say: "The citizen reported 18 people. The wider habitation model identifies 1,422 residents requiring action. These are separately labeled population scopes."

## Recalculate a disruption

13. Open **WHAT-IF**. Reduce shelter capacity to zero, optionally hospital capacity too, and select **RUN WHAT-IF SCENARIO**.
14. Compare the saved baseline and recalculation: baseline 1,422 allocated; zero shelter capacity 0 allocated and 1,422 unallocated. Zero hospital capacity shows no safe hospital.
15. Open **RELOCATION** to explain allocations, limiting capacity and remaining space.
16. In **PREDICTIVE**, use **RECALCULATE WITH SHELTER CLOSED** for a targeted disruption.

Say: "These controls call the real backend engines. They do not alter the saved operation or reserve accommodation. Overflow stays explicit."

## Finish with the responder

17. Open an assigned responder from Command, or use a visible resource ID in `/responder?unit=RESOURCE-ID`.
18. Show the simpler mobile mission screen, map, remaining ETA and status buttons. Once ON_SCENE, select RESOLVED.
19. Return to Command's audit tab to show recorded progress. All assigned units must resolve before the whole incident resolves.
20. Refresh the selected Command URL to show persistence.

Say: "The roles share one incident and assignment model. Dispatch prevents using the same unit for separate emergencies."

For another presentation, stop both servers and start again with -FreshDemo. Do not reset the normal database.

## Likely faculty questions

- **Is this AI?** It is an explainable deterministic decision-support prototype. No trained model is claimed.
- **Why not choose the nearest ambulance?** Capability, availability, travel, exposure, capacity and reserve coverage affect selection.
- **Is prediction official?** No; radial What-If simulation shows how projected risk can influence response.
- **Are beds booked?** No; hospitals and shelters use static planning capacity.
- **What works without internet?** Local reports, persistence, engines, What-If and labeled fallback movement. Road geometry and street tiles need connectivity.
- **Can authorities deploy this publicly?** Real feeds, authentication, operational validation and reservations are required before that use.
