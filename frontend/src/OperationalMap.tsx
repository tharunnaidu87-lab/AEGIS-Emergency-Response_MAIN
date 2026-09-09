import { useRoadScenario } from "./useRoadScenario";
import { useEffect, useMemo, useRef, useState } from "react";
import { Map as MapLibreMap, Marker, Popup, NavigationControl, ScaleControl, LngLatBounds, setWorkerUrl,
  type GeoJSONSource, type StyleSpecification } from "maplibre-gl";
import mapWorker from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import "maplibre-gl/dist/maplibre-gl.css";
import { updateAssignmentStatus, type Assignment, type SharedReport } from "./api";
import { assessRoadScenario, demoTravelDuration, movementProgress, prepareRoute,
  type Coordinate, type RouteSets } from "./routing";

setWorkerUrl(mapWorker);

const baseStyle: StyleSpecification = {
  version: 8,
  sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
    tileSize: 256, attribution: "OpenStreetMap contributors" } },
  layers: [
    { id: "background", type: "background", paint: { "background-color": "#172324" } },
    { id: "osm", type: "raster", source: "osm", paint: { "raster-saturation": -.8, "raster-brightness-max": .65 } },
  ],
};

function popup(title: string, detail: string) {
  const root = document.createElement("div");
  const heading = document.createElement("strong");
  heading.textContent = title;
  const description = document.createElement("p");
  description.textContent = detail;
  root.append(heading, description);
  return new Popup({ offset: 20 }).setDOMContent(root);
}

function footprint(center: Coordinate, radius: number) {
  const coordinates: Coordinate[] = [];
  for (let i = 0; i <= 64; i++) {
    const angle = i / 64 * Math.PI * 2;
    coordinates.push([center[0] + Math.cos(angle) * radius / (111.195 * Math.cos(center[1] * Math.PI / 180)),
      center[1] + Math.sin(angle) * radius / 111.195]);
  }
  return { type: "Polygon" as const, coordinates: [coordinates] };
}

type Props = { report: SharedReport; assignments: Assignment[]; routeSets: RouteSets;
  routingStatus: string; focusUnitId?: string; compact?: boolean };

export default function OperationalMap({ report, assignments, routeSets, routingStatus, focusUnitId, compact = false }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markers = useRef(new Map<string, Marker>());
  const [ready, setReady] = useState(false);
  const [mapError, setMapError] = useState("");
  const [syncError, setSyncError] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [blocked, setBlocked] = useRoadScenario(report.fusion_id);
  const [tick, setTick] = useState(Date.now);
  const initialCenter = useRef<Coordinate>([report.longitude, report.latitude]);
  const arrivalPending = useRef(new Set<string>());
  const liveUnits = useMemo(() => assignments.filter(a => !a.replaced_by_assignment_id), [assignments]);
  const selectedUnit = liveUnits.find(a => a.resource_id === (focusUnitId || selectedId)) || liveUnits[0];
  const movementStarted = liveUnits.some(a => Boolean(a.departed_at) || ["EN_ROUTE", "ON_SCENE", "RESOLVED"].includes(a.status));
  const plans = useMemo(() => liveUnits.map(assignment => {
    const routes = routeSets[assignment.resource_id] || [];
    const assessment = assessRoadScenario(routes, blocked);
    const route = routes[assessment.index] || routes[0];
    return { assignment, routes, assessment, route, sample: route ? prepareRoute(route.geometry.coordinates) : null };
  }), [liveUnits, routeSets, blocked]);
  const selectedPlan = plans.find(p => p.assignment.resource_id === selectedUnit?.resource_id);
  const result = report.analysis.result;

  useEffect(() => {
    if (!container.current) return;
    let map: MapLibreMap;
    try {
      map = new MapLibreMap({ container: container.current, style: baseStyle, center: initialCenter.current,
        zoom: 12.7, minZoom: 2, maxZoom: 19, dragRotate: false, pitchWithRotate: false });
    } catch {
      queueMicrotask(() => setMapError("WebGL map unavailable on this device. Use the incident and route details below."));
      return;
    }
    mapRef.current = map;
    const onLoad = () => setReady(true);
    const onError = () => setMapError("Basemap tiles unavailable. Coordinates, routes and calculated layers remain visible.");
    map.on("style.load", onLoad);
    map.on("error", onError);
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new ScaleControl({ unit: "metric" }));
    const observer = new ResizeObserver(() => map.resize());
    observer.observe(container.current);
    const unitMarkers = markers.current;
    return () => {
      observer.disconnect();
      map.off("style.load", onLoad);
      map.off("error", onError);
      unitMarkers.forEach(m => m.remove());
      unitMarkers.clear();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Poll the visible ETA once a second. Coordinates update outside React.
  useEffect(() => {
    const timer = setInterval(() => setTick(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (ready) mapRef.current?.easeTo({ center: [report.longitude, report.latitude], duration: 400 });
  }, [ready, report.id, report.longitude, report.latitude]);

  // Static operational features only change with the backend result.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const staticMarkers: Marker[] = [];
    function add(point: Coordinate, label: string, title: string, detail: string, color: string) {
      const element = document.createElement("button");
      element.type = "button";
      element.className = "operation-map-marker";
      element.style.borderColor = color;
      element.style.color = color;
      element.textContent = label;
      element.setAttribute("aria-label", title);
      staticMarkers.push(new Marker({ element }).setLngLat(point).setPopup(popup(title, detail)).addTo(map!));
    }
    add([report.longitude, report.latitude], "!", report.incident_type, report.location + " | " + report.people_affected + " people reported", "#ef766a");
    if (!compact) {
      for (const h of result.hazard_analysis.habitations.filter(h => h.estimated_affected_population > 0)) {
        add([h.longitude, h.latitude], h.risk_level.slice(0, 1), h.habitation_name,
          h.risk_level + " | " + h.estimated_affected_population + " modeled exposed people", h.risk_level === "RED" ? "#ef766a" : "#d6a64c");
      }
      const hospital = result.hospital_plan.selected_hospital;
      if (hospital) add([hospital.longitude, hospital.latitude], "H", hospital.name, hospital.reason || "Demo hospital capacity", "#68c99a");
      for (const shelter of result.relocation_plan?.assignments || []) {
        if (shelter.latitude !== undefined && shelter.longitude !== undefined)
          add([shelter.longitude, shelter.latitude], "S", shelter.centre_name, shelter.people_allocated + " allocated | " + shelter.remaining_capacity_after + " remaining | planning only", "#86c5eb");
      }
      for (const stage of result.prepositioning || [])
        add([stage.longitude, stage.latitude], "P", stage.resource_id + " staging recommendation", stage.reason, "#b0a0e4");
    }
    const features = [
      { type: "Feature" as const, properties: { future: true }, geometry: footprint([report.longitude, report.latitude], result.prediction?.future_radius_km || 0) },
      { type: "Feature" as const, properties: { future: false }, geometry: footprint([report.longitude, report.latitude], result.hazard_analysis.current_radius_km || 0) },
    ];
    if (!map.getSource("hazard-footprints")) {
      map.addSource("hazard-footprints", { type: "geojson", data: { type: "FeatureCollection", features } });
      map.addLayer({ id: "future-risk", type: "line", source: "hazard-footprints", filter: ["==", "future", true],
        paint: { "line-color": "#b0a0e4", "line-width": 2, "line-dasharray": [3, 3] } });
      map.addLayer({ id: "current-risk", type: "fill", source: "hazard-footprints", filter: ["==", "future", false],
        paint: { "fill-color": "#e05243", "fill-opacity": .12 } });
      map.addLayer({ id: "current-risk-edge", type: "line", source: "hazard-footprints", filter: ["==", "future", false],
        paint: { "line-color": "#e05243", "line-width": 2 } });
    } else (map.getSource("hazard-footprints") as GeoJSONSource).setData({ type: "FeatureCollection", features });
    return () => staticMarkers.forEach(marker => marker.remove());
  }, [ready, report.id, report.longitude, report.latitude, report.incident_type, report.location, report.people_affected, result, compact]);

  // Reconcile unit markers by ID instead of recreating them on every status poll.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const ids = new Set(plans.map(p => p.assignment.resource_id));
    for (const [id, marker] of markers.current) if (!ids.has(id)) { marker.remove(); markers.current.delete(id); }
    for (const plan of plans) {
      const a = plan.assignment;
      let marker = markers.current.get(a.resource_id);
      if (!marker) {
        const element = document.createElement("button");
        element.type = "button"; element.className = "aegis-resource-marker";
        element.textContent = a.resource_id;
        element.setAttribute("aria-label", a.resource_id + " simulated unit");
        element.dataset.resourceId = a.resource_id;
        marker = new Marker({ element }).setLngLat([a.start_longitude, a.start_latitude]).addTo(map);
        markers.current.set(a.resource_id, marker);
      }
      marker.setPopup(popup(a.resource_id, a.status + " | SIMULATED MOVEMENT | " + plan.assessment.reason));
      const position = plan.route && plan.sample ? plan.sample(movementProgress(a, plan.route, Date.now())) : [a.start_longitude, a.start_latitude] as Coordinate;
      if (position) marker.setLngLat(position);
    }
  }, [ready, plans]);

  useEffect(() => {
    if (!ready) return;
    let frame = 0;
    function animate() {
      let moving = false;
      for (const { assignment: a, route, sample } of plans) {
        if (a.status !== "EN_ROUTE" || !route || !sample) continue;
        const progress = movementProgress(a, route, Date.now());
        const position = sample(progress);
        const marker = markers.current.get(a.resource_id);
        if (position && marker) {
          marker.setLngLat(position);
          marker.getElement().dataset.progress = progress.toFixed(4);
        }
        if (progress < 1) moving = true;
      }
      if (moving) frame = requestAnimationFrame(animate);
    }
    frame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frame);
  }, [ready, plans]);

  // Arrival is a demo status transition; backend validates/idempotently stores it.
  useEffect(() => {
    const timers: ReturnType<typeof setTimeout>[] = [];
    for (const { assignment: a, route } of plans) {
      if (a.status !== "EN_ROUTE" || !route) continue;
      const due = Date.parse(a.departed_at || a.updated_at) + demoTravelDuration(route) - Date.now();
      timers.push(setTimeout(() => {
        if (arrivalPending.current.has(a.id)) return;
        arrivalPending.current.add(a.id);
        void updateAssignmentStatus(a.id, "ON_SCENE").then(() => setSyncError("")).catch(error => {
          arrivalPending.current.delete(a.id);
          setSyncError(error instanceof Error ? error.message : "Arrival sync failed; use responder status controls.");
        });
      }, Math.max(100, due)));
    }
    return () => timers.forEach(clearTimeout);
  }, [plans]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const features = plans.flatMap(plan => plan.routes.map((route, index) => ({
      type: "Feature" as const,
      properties: { chosen: index === plan.assessment.index, selected: plan.assignment.resource_id === selectedUnit?.resource_id, fallback: route.source === "FALLBACK" },
      geometry: route.geometry,
    })));
    if (!map.getSource("response-routes")) {
      map.addSource("response-routes", { type: "geojson", data: { type: "FeatureCollection", features } });
      map.addLayer({ id: "response-routes", type: "line", source: "response-routes",
        paint: { "line-color": ["case", ["get", "fallback"], "#d6a64c", ["get", "chosen"], "#78cbb3", "#718899"],
          "line-width": ["case", ["all", ["get", "chosen"], ["get", "selected"]], 5, 2],
          "line-opacity": ["case", ["get", "chosen"], .95, .45] } });
    } else (map.getSource("response-routes") as GeoJSONSource).setData({ type: "FeatureCollection", features });
    const hazard = selectedPlan?.assessment.hazard;
    let marker: Marker | undefined;
    if (hazard) {
      const element = document.createElement("div");
      element.className = "operation-map-marker hazard"; element.textContent = "X";
      marker = new Marker({ element }).setLngLat(hazard).setPopup(popup("SIMULATED BLOCKED SEGMENT", selectedPlan!.assessment.reason)).addTo(map);
    }
    return () => { marker?.remove(); };
  }, [ready, plans, selectedPlan, selectedUnit?.resource_id]);

  function fitOperation() {
    const bounds = new LngLatBounds([report.longitude, report.latitude], [report.longitude, report.latitude]);
    for (const plan of plans) for (const point of plan.route?.geometry.coordinates || []) bounds.extend(point);
    for (const shelter of result.relocation_plan?.assignments || [])
      if (shelter.latitude !== undefined && shelter.longitude !== undefined) bounds.extend([shelter.longitude, shelter.latitude]);
    mapRef.current?.fitBounds(bounds, { padding: 60, maxZoom: 14, duration: 400 });
  }

  const progress = selectedPlan?.route ? movementProgress(selectedPlan.assignment, selectedPlan.route, tick) : 0;
  const eta = selectedPlan?.route ? Math.ceil(selectedPlan.route.duration * (1 - progress) / 60) : selectedUnit?.eta_minutes;
  return <section className="operation-map" aria-label="Operational map">
    <div className="vector-map-shell">
      <div ref={container} className="vector-operational-map" style={{ minHeight: compact ? 340 : 460 }} />
      <div className="vector-map-actions"><button onClick={fitOperation}>FIT OPERATION</button></div>
      <div className="map-legend"><span>! INCIDENT</span><span className="danger">CURRENT DANGER</span><span className="future">DASHED: FUTURE RISK</span><span>H HOSPITAL | S SHELTER | P STAGING</span></div>
      {mapError && <p className="map-service-note" role="status">{mapError}</p>}
    </div>
    <div className="route-status-panel">
      <div className="route-panel-heading"><strong>{routingStatus}</strong><small>DEMO INFRASTRUCTURE | SIMULATED MOVEMENT (18-55 s)</small></div>
      {liveUnits.length > 0 && <div className="route-unit-controls">
        <label>Response unit <select value={selectedUnit?.resource_id || ""} onChange={e => setSelectedId(e.target.value)}>
          {liveUnits.map(a => <option key={a.id} value={a.resource_id}>{a.resource_id} | {a.status}</option>)}
        </select></label>
        <button disabled={movementStarted} aria-pressed={blocked} onClick={() => setBlocked(!blocked)}>
          {blocked ? "CLEAR SIMULATED ROAD BLOCK" : "SIMULATE BLOCKED ROAD"}
        </button>
        <span>{eta === undefined ? "ETA pending" : eta + " MIN REMAINING"} | {Math.round(progress * 100)}% SIMULATED JOURNEY</span>
      </div>}
      <p>{selectedPlan?.assessment.reason || "Dispatch resources to calculate routes."}</p>
      {movementStarted && <small>Road scenario is fixed for this simulated journey. Use What-If to compare a new road disruption.</small>}
      {selectedUnit?.resource_type === "RESCUE_BOAT" && <small>Driving route represents boat transport to the incident, not water navigation.</small>}
      {syncError && <p className="form-alert" role="alert">{syncError}</p>}
    </div>
  </section>;
}
