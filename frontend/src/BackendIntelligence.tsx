import type { AegisResult } from "./api";

export default function BackendIntelligence({ result, condensed = false }: { result: AegisResult; condensed?: boolean }) {
  const prediction = result.prediction;
  return <section className={"backend-intelligence" + (condensed ? " condensed" : "")} aria-label="Incident assessment">
    <div className="decision-summary"><strong>Incident assessment and response considerations</strong>
      <p>{result.incident.type === 'SOS' ? 'Unknown emergency: precautionary high priority. No hazard footprint is inferred from SOS alone.' : `Estimated hazard footprint: ${result.hazard_analysis.current_radius_km ?? 0} km radius. ${result.hazard_analysis.total_population_requiring_action} people in modelled habitation exposure require action.`}</p>
      <p>Immediate / short-term / medium-term population: {result.hazard_analysis.priority_summary.immediate_population} / {result.hazard_analysis.priority_summary.short_term_population} / {result.hazard_analysis.priority_summary.medium_term_population}. Safe relocation allocation: {result.relocation_plan?.total_allocated ?? 0}; unmet demand: {result.relocation_plan?.unallocated_people ?? 0}.</p>
      <p>Capacity is limited by the lowest space, water, food, sanitation or medical provision, less occupancy. Destination allocations are planning estimates, not reservations.</p>
      <p>All resources, availability, projections, and movement are simulated. Review each recommendation before approving a demonstration dispatch.</p>
    </div>
    <div className="intelligence-metrics">
      <div><small>SEVERITY / 100</small><strong>{result.severity_analysis.risk_score} / {result.severity_analysis.severity}</strong></div>
      <div><small>EVIDENCE QUALITY / 100</small><strong>{result.confidence_analysis?.score ?? "Unavailable"}</strong></div>
      <div><small>INCIDENT PRIORITY / 100</small><strong>{result.priority_analysis?.score ?? "Unavailable"}</strong></div>
      <div><small>CORROBORATING REPORTS</small><strong>{result.confidence_analysis?.report_count ?? 1}</strong></div>
    </div>
    <p className="intelligence-note">Rule-based prototype. Evidence quality is not a probability; reporter identities are not verified. Infrastructure uses local demo data.</p>
    <details><summary>How were severity and evidence quality assessed?</summary>
      <div className="factor-grid">
        <div><strong>Severity factors</strong>{Object.entries(result.severity_analysis.factors || {}).filter(([, value]) => value > 0).map(([key, value]) => <p key={key}>{key.replaceAll("_", " ")} <b>+{value}</b></p>)}</div>
        <div><strong>Evidence factors</strong>{Object.entries(result.confidence_analysis?.factors || {}).map(([key, value]) => <p key={key}>{key.replaceAll("_", " ")} <b>+{value}</b></p>)}</div>
      </div>
    </details>
    {!condensed && <>
      {prediction && <div className="prediction-summary">
        <div><small>CURRENT DANGER FOOTPRINT</small><strong>{prediction.current_radius_km.toFixed(2)} km radius</strong></div>
        <div><small>SIMULATED +{prediction.horizon_minutes} MIN</small><strong>{prediction.future_radius_km.toFixed(2)} km radius</strong></div>
        <div><small>ADDITIONAL POPULATION AT RISK</small><strong>{prediction.additional_population_at_risk}</strong></div>
        <p>{prediction.assumptions}</p>
      </div>}
      <div className="staging-recommendations"><h3>RESOURCE STAGING RECOMMENDATIONS</h3>
        {(result.prepositioning || []).length ? result.prepositioning!.map(item => <article key={item.resource_id}>
          <strong>{item.resource_id} to {item.zone_name}</strong><p>{item.reason}</p>
          <small>{item.eta_minutes} MIN ESTIMATED TO STAGING | RECOMMENDATION ONLY</small>
        </article>) : <p>No compatible spare unit or increasing high-risk zone qualifies for staging.</p>}
      </div>
      <p className="intelligence-note">{result.population_basis}</p>
      {result.hazard_analysis.data_coverage === "OUTSIDE_DEMO_AREA" && <p className="form-alert">This report is outside the local infrastructure dataset. Local population exposure and nearby destinations are unavailable.</p>}
    </>}
  </section>;
}
