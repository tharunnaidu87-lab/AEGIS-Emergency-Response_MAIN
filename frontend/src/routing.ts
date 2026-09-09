import { useEffect, useMemo, useState } from "react";
import type { Assignment, SharedReport } from "./api";

export type Coordinate = [number, number];
export type RoadRoute = {
  distance: number; duration: number;
  geometry: { type: "LineString"; coordinates: Coordinate[] };
  source: "OSRM" | "FALLBACK";
};
export type RouteSets = Record<string, RoadRoute[]>;

export function distanceKm(a: Coordinate, b: Coordinate) {
  const rad = Math.PI / 180;
  const value = Math.sin((b[1] - a[1]) * rad / 2) ** 2 +
    Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin((b[0] - a[0]) * rad / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(Math.min(1, Math.max(0, value))));
}

// Compute cumulative lengths once. Frame updates use binary search.
export function prepareRoute(coordinates: Coordinate[]) {
  const distances = [0];
  for (let i = 1; i < coordinates.length; i++) {
    distances.push(distances[i - 1] + distanceKm(coordinates[i - 1], coordinates[i]));
  }
  const total = distances.at(-1) ?? 0;
  return (progress: number): Coordinate | undefined => {
    if (!coordinates.length) return undefined;
    if (progress <= 0 || total === 0) return coordinates[0];
    if (progress >= 1) return coordinates.at(-1);
    const target = total * progress;
    let low = 1, high = distances.length - 1;
    while (low < high) {
      const mid = Math.floor((low + high) / 2);
      if (distances[mid] < target) low = mid + 1; else high = mid;
    }
    const span = distances[low] - distances[low - 1];
    const ratio = span ? (target - distances[low - 1]) / span : 0;
    const start = coordinates[low - 1], end = coordinates[low];
    return [start[0] + (end[0] - start[0]) * ratio, start[1] + (end[1] - start[1]) * ratio];
  };
}

export function demoTravelDuration(route: RoadRoute) {
  return Math.max(18000, Math.min(55000, route.duration * 1000 / 25));
}

export function movementProgress(assignment: Assignment, route: RoadRoute, now: number) {
  if (assignment.status === "ON_SCENE" || assignment.status === "RESOLVED") return 1;
  if (!assignment.departed_at && assignment.status !== "EN_ROUTE") return 0;
  const start = Date.parse(assignment.departed_at || assignment.updated_at);
  const clock = assignment.status === "ISSUE" ? Date.parse(assignment.updated_at) : now;
  return Math.min(1, Math.max(0, (clock - start) / demoTravelDuration(route)));
}

const cache = new Map<string, { expires: number; promise: Promise<RoadRoute[]> }>();

export function fetchRoadRoutes(start: Coordinate, end: Coordinate): Promise<RoadRoute[]> {
  const key = start.join(",") + ";" + end.join(",");
  const cached = cache.get(key);
  if (cached && cached.expires > Date.now()) return cached.promise;
  const promise = (async () => {
    try {
      const base = (import.meta.env.VITE_OSRM_URL || "https://router.project-osrm.org").replace(/\/$/, "");
      const response = await fetch(base + "/route/v1/driving/" + key + "?alternatives=2&steps=false&geometries=geojson&overview=full",
        { signal: AbortSignal.timeout(6000) });
      if (!response.ok) throw new Error("Routing unavailable");
      const body = await response.json() as { code: string; routes?: RoadRoute[] };
      const valid = body.routes?.filter(r => r.geometry?.coordinates?.length >= 2 &&
        Number.isFinite(r.duration) && r.duration >= 0 && Number.isFinite(r.distance) &&
        r.geometry.coordinates.every(p => p.length >= 2 && Number.isFinite(p[0]) && Number.isFinite(p[1])));
      if (body.code !== "Ok" || !valid?.length) throw new Error("No road route returned");
      return valid.map(r => ({ ...r, source: "OSRM" as const }));
    } catch {
      const distance = distanceKm(start, end) * 1000;
      return [{ distance, duration: Math.max(60, distance / 1000 / 25 * 3600),
        geometry: { type: "LineString" as const, coordinates: [start, end] }, source: "FALLBACK" as const }];
    }
  })();
  if (cache.size > 100) cache.delete(cache.keys().next().value!);
  cache.set(key, { expires: Date.now() + 5 * 60 * 1000, promise });
  return promise;
}

export function useRoadRoutes(report: SharedReport | undefined, assignments: Assignment[]) {
  const [routes, setRoutes] = useState<RouteSets>({});
  const [status, setStatus] = useState("WAITING FOR DISPATCH");
  const signature = JSON.stringify(assignments.filter(a => !a.replaced_by_assignment_id)
    .map(a => [a.resource_id, a.start_longitude, a.start_latitude]).sort());
  const units = useMemo(() => JSON.parse(signature) as [string, number, number][], [signature]);
  const longitude = report?.longitude, latitude = report?.latitude;
  useEffect(() => {
    let active = true;
    async function load() {
      if (longitude === undefined || latitude === undefined || !units.length) {
        if (active) { setRoutes({}); setStatus("WAITING FOR DISPATCH"); }
        return;
      }
      setRoutes({});
      setStatus("CALCULATING ROAD ROUTES");
      const results = await Promise.all(units.map(async ([id, lng, lat]) =>
        [id, await fetchRoadRoutes([lng, lat], [longitude, latitude])] as const));
      if (!active) return;
      const next = Object.fromEntries(results);
      setRoutes(next);
      const fallback = Object.values(next).filter(r => r[0]?.source === "FALLBACK").length;
      setStatus(fallback ? "ESTIMATED STRAIGHT-LINE FALLBACK (" + fallback + " UNITS)" : "OSRM ROAD ROUTES READY");
    }
    void load();
    return () => { active = false; };
  }, [longitude, latitude, units]);
  return { routes, status };
}

// A blocked segment is a DEMO scenario. Choose a less exposed OSRM alternative
// before departure; never invent a road detour if the routing service has none.
export function assessRoadScenario(routes: RoadRoute[], blocked: boolean) {
  const primary = routes[0];
  if (!primary) return { index: 0, hazard: undefined, reason: "Awaiting route calculation", scores: [] as number[] };
  if (!blocked) return { index: 0, hazard: undefined, reason: primary.source === "OSRM" ? "Fastest returned driving route" : "Estimated straight line; road access unverified", scores: [] as number[] };
  if (primary.source === "FALLBACK") return { index: 0, hazard: undefined, reason: "Road closure cannot be evaluated on a straight-line fallback. Route requires operator verification.", scores: [] as number[] };
  const sample = prepareRoute(primary.geometry.coordinates);
  const hazard = sample(.5)!;
  const scores = routes.map(route => {
    // The closure's 120 m exclusion area is compared with sampled road geometry.
    const point = prepareRoute(route.geometry.coordinates);
    let minimum = Infinity;
    for (let i = 0; i <= 100; i++) minimum = Math.min(minimum, distanceKm(hazard, point(i / 100)!));
    return (minimum < .12 ? 1000 : 0) + route.duration / 60;
  });
  const index = scores.indexOf(Math.min(...scores));
  const safe = scores[index] < 1000;
  return { index: safe ? index : 0, hazard, scores,
    reason: safe && index > 0 ? "Simulated blocked segment: less exposed OSRM alternative selected" :
      "Simulated blocked segment: no clear OSRM alternative; operator verification required" };
}
