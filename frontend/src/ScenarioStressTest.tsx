import { useState } from "react";
import { runAegisAnalysis, type AegisResponse, type SharedReport } from "./api";

export default function ScenarioStressTest({ report, mode }: { report: SharedReport; mode: "shelter" | "road" }) {
  const [closed, setClosed] = useState("");
  const [result, setResult] = useState<AegisResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const centres = report.analysis.result.relocation_plan?.assignments || [];
  const centreId = closed || centres[0]?.centre_id || "";
  async function run() {
    setBusy(true); setError(""); setResult(null);
    const incident = report.analysis.result.incident;
    try {
      setResult(await runAegisAnalysis({
        report_id: report.id, incident_type: report.incident_type, location: incident.location,
        latitude: incident.latitude, longitude: incident.longitude, people_affected: incident.reported_people_affected,
        description: incident.description, hazard_intensity: incident.hazard_intensity,
        injured: incident.injured || 0, trapped: incident.trapped || 0, vulnerable_groups: report.vulnerable_groups,
        gps_verified: report.gps_verified, spreading: report.spreading, structural_damage: report.structural_damage,
        scenario: mode === "shelter" ? { closed_shelter_ids: [centreId] } : { road_blocked: true },
      }));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Scenario analysis failed."); }
    finally { setBusy(false); }
  }
  return <div className="scenario-stress">
    {mode === "shelter" && <label>Close a planned shelter<select value={centreId} onChange={e => { setClosed(e.target.value); setResult(null); }}>
      {centres.map(c => <option key={c.centre_id} value={c.centre_id}>{c.centre_name}</option>)}
    </select></label>}
    <button disabled={busy || (mode === "shelter" && !centreId)} onClick={() => { void run(); }}>
      {busy ? "RECALCULATING..." : mode === "shelter" ? "ASSESS SHELTER CLOSURE" : "ASSESS ROAD DISRUPTION"}
    </button>
    {error && <p role="alert" className="form-alert">{error}</p>}
    {result && <div aria-live="polite">
      {mode === "shelter" ? <>
        <p><b>{result.result.relocation_plan?.total_allocated ?? 0}</b> people allocated · <b>{result.result.relocation_plan?.unallocated_people ?? 0}</b> unallocated</p>
        {result.result.relocation_plan?.assignments.map(a => <p key={a.centre_id}>{a.centre_name}: {a.people_allocated} allocated, {a.remaining_capacity_after} capacity left</p>)}
      </> : <>
        {result.result.resource_plan.selected_resources.map(r => <p key={r.id}>{r.id}: {r.eta_minutes} min estimated travel with road disruption</p>)}
        <p>Route geometry and alternatives are evaluated on the map. This scenario changes the backend travel cost by 50%.</p>
      </>}
    </div>}
    <small>Isolated scenario analysis · saved incident and dispatch records remain unchanged.</small>
  </div>;
}
