import BackendIntelligence from "./BackendIntelligence";
import ScenarioStressTest from "./ScenarioStressTest";
import { canonicalReportId } from "./api";
import { useEffect, useMemo, useState, type ReactNode, } from "react";
import { listAuditEvents, reassignAssignment, type Assignment, type AuditEvent, type SharedReport, } from "./api";
export type UnifiedCommandView = "INTELLIGENCE" | "FIELD_OPS" | "PREDICTIVE" | "COORDINATION" | "AUDIT";
type Props = {
    view: UnifiedCommandView;
    selected: SharedReport;
    reports: SharedReport[];
    assignments: Assignment[];
    onRefresh: () => Promise<void> | void;
};
type Capability = "AMBULANCE" | "POLICE" | "FIRE" | "BOAT" | "RESCUE" | "DRONE" | "OTHER";
type ForecastZone = {
    id: string;
    name: string;
    currentLevel: string;
    currentScore: number;
    forecastLevel: string;
    forecastScore: number;
    population: number;
    priority: string;
};
type ShortageRow = {
    capability: Capability;
    required: number;
    active: number;
    shortage: number;
};
type ConflictRow = {
    capability: Capability;
    required: number;
    active: number;
    incidents: number;
    pressure: number;
};
type CascadeAlert = {
    level: "CRITICAL" | "WARNING" | "ADVISORY";
    title: string;
    detail: string;
};
function capabilityFromText(value: string): Capability {
    const text = value
        .toLowerCase()
        .replace(/[_-]/g, " ");
    if (text.includes("ambulance")
        || text.includes("medical")
        || text.includes("ems")) {
        return "AMBULANCE";
    }
    if (text.includes("police")
        || text.includes("security")) {
        return "POLICE";
    }
    if (text.includes("fire")) {
        return "FIRE";
    }
    if (text.includes("boat")
        || text.includes("marine")
        || text.includes("water rescue")) {
        return "BOAT";
    }
    if (text.includes("rescue")) {
        return "RESCUE";
    }
    if (text.includes("drone")) {
        return "DRONE";
    }
    return "OTHER";
}
function ageMinutes(timestamp: string) {
    const parsed = Date.parse(timestamp);
    if (!Number.isFinite(parsed)) {
        return 0;
    }
    return Math.max(0, (Date.now() - parsed) / 60000);
}
function timeLabel(value: string) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return value;
    }
    return date.toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
    });
}
function statusProgress(status: string) {
    switch (status) {
        case "REPORTED":
            return 10;
        case "ACKNOWLEDGED":
            return 25;
        case "DISPATCHED":
            return 45;
        case "EN_ROUTE":
            return 65;
        case "ON_SCENE":
            return 85;
        case "RESOLVED":
            return 100;
        default:
            return 0;
    }
}
function fusionReports(selected: SharedReport, reports: SharedReport[]) {
    return reports
        .filter(report => report.fusion_id === selected.fusion_id)
        .sort((first, second) => Date.parse(first.created_at)
        - Date.parse(second.created_at));
}
function priorityScore(report: SharedReport, _relatedReports = 1) { return report.analysis.result.priority_analysis?.score ?? report.analysis.result.severity_analysis.risk_score; }
function forecastZones(report: SharedReport): ForecastZone[] {
    return (report.analysis.result.prediction?.habitations || []).map(h => ({
        id: h.habitation_id, name: h.habitation_name, currentLevel: h.current_risk_level,
        currentScore: h.current_risk_score, forecastLevel: h.risk_level, forecastScore: h.risk_score,
        population: h.estimated_affected_population, priority: h.relocation_priority,
    }));
}
function incidentReports(reports: SharedReport[]) {
    return [...new Map(reports.map(r => [r.fusion_id, r])).values()];
}
function buildCascadeAlerts(report: SharedReport, assignments: Assignment[], confidence: number): CascadeAlert[] {
    const alerts: CascadeAlert[] = [];
    const redZones = report.analysis.result.hazard_analysis.habitations
        .filter(habitation => habitation.risk_level === "RED");
    if (report.spreading && report.structural_damage) {
        alerts.push({
            level: "CRITICAL",
            title: "COMPOUND HAZARD",
            detail: "Hazard propagation and structural damage are both active.",
        });
    }
    else if (report.spreading) {
        alerts.push({
            level: "WARNING",
            title: "HAZARD PROPAGATION",
            detail: "The incident is marked as spreading into adjacent exposure areas.",
        });
    }
    if (redZones.length > 0) {
        alerts.push({
            level: "CRITICAL",
            title: `${redZones.length} RED-ZONE HABITATION${redZones.length > 1 ? "S" : ""}`,
            detail: "Immediate protective-action zones exist in the current hazard analysis.",
        });
    }
    const relocation = report.analysis.result.people_requiring_relocation;
    if (relocation > 0) {
        alerts.push({
            level: relocation >= 500 ? "CRITICAL" : "WARNING",
            title: "POPULATION DISPLACEMENT",
            detail: `${relocation} people currently require relocation planning.`,
        });
    }
    const issues = assignments.filter(assignment => assignment.report_id === canonicalReportId(report)
        && assignment.status === "ISSUE"
        && !assignment.replaced_by_assignment_id).length;
    if (issues > 0) {
        alerts.push({
            level: "WARNING",
            title: "FIELD CAPABILITY LOSS",
            detail: `${issues} assigned unit${issues === 1 ? "" : "s"} currently report ISSUE.`,
        });
    }
    if (confidence < 55) {
        alerts.push({
            level: "ADVISORY",
            title: "LOW EVIDENCE CONFIDENCE",
            detail: "Additional independent reports or verified GPS would improve confidence.",
        });
    }
    if (alerts.length === 0) {
        alerts.push({
            level: "ADVISORY",
            title: "NO CASCADING ALERT",
            detail: "No additional compound-risk condition is detected for this incident.",
        });
    }
    return alerts;
}
function selectedRequirements(report: SharedReport) {
    const map = new Map<Capability, number>();
    Object.entries(report.analysis.result.resource_plan.required_resources).forEach(([type, rawCount]) => {
        const capability = capabilityFromText(type);
        const count = Number(rawCount) || 0;
        if (count <= 0) {
            return;
        }
        map.set(capability, (map.get(capability) ?? 0) + count);
    });
    return map;
}
function shortageRows(report: SharedReport, assignments: Assignment[]): ShortageRow[] {
    const requirements = selectedRequirements(report);
    return Array.from(requirements.entries())
        .map(([capability, required]) => {
        const active = assignments.filter(assignment => {
            if (assignment.report_id !== canonicalReportId(report)) {
                return false;
            }
            if (assignment.status === "RESOLVED"
                || assignment.status === "ISSUE") {
                return false;
            }
            return (capabilityFromText(assignment.resource_type)
                === capability);
        }).length;
        return {
            capability,
            required,
            active,
            shortage: Math.max(0, required - active),
        };
    })
        .sort((first, second) => second.shortage - first.shortage);
}
function resourcePool(reports: SharedReport[]) {
    const map = new Map<string, {
        id: string;
        type: string;
        capability: Capability;
        status: string;
    }>();
    reports.forEach(report => {
        (report.analysis.result.resource_plan.catalog || report.analysis.result.resource_plan.selected_resources)
            .forEach(resource => {
            if (!map.has(resource.id)) {
                map.set(resource.id, {
                    id: resource.id,
                    type: resource.type,
                    capability: capabilityFromText(resource.type),
                    status: resource.status,
                });
            }
        });
    });
    return Array.from(map.values());
}
function conflictRows(reports: SharedReport[], assignments: Assignment[]): ConflictRow[] {
    const activeReports = incidentReports(reports).filter(report => report.status !== "RESOLVED");
    const capabilities: Capability[] = [
        "AMBULANCE",
        "POLICE",
        "FIRE",
        "BOAT",
        "RESCUE",
        "DRONE",
    ];
    return capabilities
        .map(capability => {
        let required = 0;
        let incidents = 0;
        activeReports.forEach(report => {
            const count = selectedRequirements(report).get(capability) ?? 0;
            if (count > 0) {
                required += count;
                incidents += 1;
            }
        });
        const active = assignments.filter(assignment => {
            if (assignment.status === "RESOLVED"
                || assignment.status === "ISSUE") {
                return false;
            }
            return (capabilityFromText(assignment.resource_type)
                === capability);
        }).length;
        const pressure = required === 0
            ? 0
            : Math.round((required / Math.max(1, active)) * 100);
        return {
            capability,
            required,
            active,
            incidents,
            pressure,
        };
    })
        .filter(row => row.required > 0)
        .sort((first, second) => second.pressure - first.pressure);
}
function systemStress(reports: SharedReport[], assignments: Assignment[], conflicts: ConflictRow[]) {
    const active = incidentReports(reports).filter(report => report.status !== "RESOLVED");
    const severe = active.filter(report => report.analysis.result.severity_analysis.risk_score >= 70).length;
    const red = active.filter(report => report.analysis.result.hazard_analysis.habitations
        .some(habitation => habitation.risk_level === "RED")).length;
    const delayed = active.filter(report => {
        const age = ageMinutes(report.created_at);
        return (age >= 25
            && report.status !== "ON_SCENE");
    }).length;
    const issues = assignments.filter(assignment => assignment.status === "ISSUE"
        && !assignment.replaced_by_assignment_id).length;
    const overloaded = conflicts.filter(conflict => conflict.pressure > 125).length;
    const relocation = active.reduce((total, report) => total
        + report.analysis.result.people_requiring_relocation, 0);
    let score = 0;
    score += Math.min(20, active.length * 5);
    score += Math.min(20, severe * 8);
    score += Math.min(16, red * 8);
    score += Math.min(16, delayed * 7);
    score += Math.min(12, issues * 6);
    score += Math.min(10, overloaded * 5);
    if (relocation >= 1000) {
        score += 10;
    }
    else if (relocation >= 300) {
        score += 6;
    }
    else if (relocation > 0) {
        score += 3;
    }
    score = Math.min(100, Math.round(score));
    const level = score >= 80
        ? "CRITICAL"
        : score >= 60
            ? "HIGH"
            : score >= 35
                ? "MODERATE"
                : "LOW";
    return {
        score,
        level,
        active: active.length,
        severe,
        red,
        delayed,
        issues,
        relocation,
    };
}
function readinessScore(reports: SharedReport[], assignments: Assignment[]) {
    const active = incidentReports(reports).filter(report => report.status !== "RESOLVED");
    if (active.length === 0) {
        return {
            score: 100,
            level: "READY",
            resourceCoverage: 100,
            fieldHealth: 100,
            relocationReadiness: 100,
            workflowProgress: 100,
        };
    }
    let required = 0;
    let assigned = 0;
    active.forEach(report => {
        required += Array.from(selectedRequirements(report).values()).reduce((total, value) => total + value, 0);
        assigned += assignments.filter(assignment => assignment.report_id === canonicalReportId(report)
            && assignment.status !== "RESOLVED"
            && assignment.status !== "ISSUE").length;
    });
    const resourceCoverage = required === 0
        ? 100
        : Math.min(100, Math.round((assigned / required) * 100));
    const activeAssignments = assignments.filter(assignment => assignment.status !== "RESOLVED");
    const issueAssignments = activeAssignments.filter(assignment => assignment.status === "ISSUE").length;
    const fieldHealth = activeAssignments.length === 0
        ? 100
        : Math.max(0, Math.round(100
            - (issueAssignments / activeAssignments.length) * 100));
    const relocationReports = active.filter(report => report.analysis.result.people_requiring_relocation > 0);
    const relocationReadiness = relocationReports.length === 0
        ? 100
        : Math.round(relocationReports.reduce((total, report) => total
            + (report.analysis.result.relocation_plan
                ?.coverage_percent
                ?? 0), 0) / relocationReports.length);
    const workflowProgress = Math.round(active.reduce((total, report) => total + statusProgress(report.status), 0) / active.length);
    const score = Math.max(0, Math.min(100, Math.round(resourceCoverage * 0.38
        + fieldHealth * 0.22
        + relocationReadiness * 0.2
        + workflowProgress * 0.2)));
    const level = score < 45
        ? "CRITICAL"
        : score < 65
            ? "STRAINED"
            : score < 82
                ? "ELEVATED"
                : "READY";
    return {
        score,
        level,
        resourceCoverage,
        fieldHealth,
        relocationReadiness,
        workflowProgress,
    };
}
function afterActionMetrics(reports: SharedReport[], assignments: Assignment[]) {
    return reports
        .filter(report => report.status === "RESOLVED")
        .map(report => {
        const created = Date.parse(report.created_at);
        const updated = Date.parse(report.updated_at);
        const duration = Number.isFinite(created)
            && Number.isFinite(updated)
            ? Math.max(0, (updated - created) / 60000)
            : 0;
        const reportAssignments = assignments.filter(assignment => assignment.report_id === canonicalReportId(report));
        return {
            report,
            duration,
            units: reportAssignments.length,
            risk: report.analysis.result.severity_analysis.risk_score,
        };
    })
        .sort((first, second) => Date.parse(second.report.updated_at)
        - Date.parse(first.report.updated_at));
}
function UnifiedCommandModules({ view, selected, reports, assignments, onRefresh, }: Props) {
    const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
    const [auditOnline, setAuditOnline] = useState(true);
    const [reassigning, setReassigning] = useState("");
    const [actionMessage, setActionMessage] = useState("");
    
    const [completedChecklist, setCompletedChecklist] = useState<Record<string, string[]>>({});
    const group = useMemo(() => fusionReports(selected, reports), [selected, reports]);
    const confidence = selected.analysis.result.confidence_analysis?.score ?? 0;
    const selectedPriority = useMemo(() => priorityScore(selected, group.length), [selected, group.length]);
    const zones = useMemo(() => forecastZones(selected), [selected]);
    const cascade = useMemo(() => buildCascadeAlerts(selected, assignments, confidence), [selected, assignments, confidence]);
    const shortages = useMemo(() => shortageRows(selected, assignments), [selected, assignments]);
    const pool = useMemo(() => resourcePool(reports), [reports]);
    const conflicts = useMemo(() => conflictRows(reports, assignments), [reports, assignments]);
    const stress = useMemo(() => systemStress(reports, assignments, conflicts), [reports, assignments, conflicts]);
    const readiness = useMemo(() => readinessScore(reports, assignments), [reports, assignments]);
    const resolved = useMemo(() => afterActionMetrics(reports, assignments), [reports, assignments]);
    const selectedAssignments = useMemo(() => assignments.filter(assignment => assignment.report_id === canonicalReportId(selected)), [assignments, selected]);
    const unresolvedIssues = useMemo(() => assignments.filter(assignment => assignment.status === "ISSUE"
        && !assignment.replaced_by_assignment_id), [assignments]);
    const replacementAssignments = useMemo(() => assignments.filter(assignment => Boolean(assignment.replaces_assignment_id)), [assignments]);
    useEffect(() => {
        if (view !== "AUDIT") {
            return;
        }
        let active = true;
        async function refreshAudit() {
            try {
                const events = await listAuditEvents({
                    fusionId: selected.fusion_id,
                    limit: 250,
                });
                if (!active) {
                    return;
                }
                setAuditEvents(events);
                setAuditOnline(true);
            }
            catch (error) {
                console.error(error);
                if (active) {
                    setAuditOnline(false);
                }
            }
        }
        void refreshAudit();
        const timer = window.setInterval(() => {
            void refreshAudit();
        }, 2500);
        return () => {
            active = false;
            window.clearInterval(timer);
        };
    }, [
        view,
        selected.fusion_id,
    ]);
    async function handleReassign(assignment: Assignment) {
        setReassigning(assignment.id);
        setActionMessage("");
        try {
            const result = await reassignAssignment(assignment.id, "UNIT_ISSUE");
            if (result.replacement_assignment) {
                setActionMessage(`${result.original_assignment.resource_id} → ${result.replacement_assignment.resource_id} reassignment stored in SQLite.`);
            }
            else {
                setActionMessage("Reassignment request completed without a new replacement record.");
            }
            await onRefresh();
        }
        catch (error) {
            console.error(error);
            setActionMessage(error instanceof Error
                ? error.message
                : "AEGIS reassignment failed.");
        }
        finally {
            setReassigning("");
        }
    }
    const topZone = zones[0];
    const priorityQueue = incidentReports(reports)
        .filter(report => report.status !== "RESOLVED")
        .map(report => {
        const related = fusionReports(report, reports).length;
        return {
            report,
            priority: priorityScore(report, related),
        };
    })
        .sort((first, second) => second.priority - first.priority);
    const resourceStates = pool.map(resource => {
        const activeAssignment = assignments.find(assignment => assignment.resource_id === resource.id
            && assignment.status !== "RESOLVED");
        const state = activeAssignment?.status === "ISSUE"
            ? "ISSUE"
            : activeAssignment
                ? "BUSY"
                : resource.status;
        return {
            ...resource,
            state,
            assignment: activeAssignment,
        };
    });
    const freeResources = resourceStates.filter(resource => resource.state === "AVAILABLE");
    const activeResourceIds = new Set(assignments
        .filter(assignment => assignment.status !== "RESOLVED")
        .map(assignment => assignment.resource_id));
    const backupRecommendations = shortages
        .filter(row => row.shortage > 0)
        .map(row => ({
        ...row,
        candidates: (selected.analysis.result.resource_plan.catalog || selected.analysis.result.resource_plan.selected_resources)
            .filter(resource => capabilityFromText(resource.type)
            === row.capability
            && resource.status === "AVAILABLE" && !activeResourceIds.has(resource.id))
            .slice(0, row.shortage),
    }));
    const demandForecast = shortages.map(row => {
        const forecast = selected.analysis.result.prediction?.future_resource_requirements || {};
        const predictedRequired = Object.entries(forecast).filter(([kind]) => capabilityFromText(kind) === row.capability).reduce((sum, [,n]) => sum + n, 0);
        return { ...row, predictedRequired, predictedGap: Math.max(0, predictedRequired - row.active) };
    });
    const mutualAidCapabilities = conflicts
        .filter(conflict => conflict.pressure > 110)
        .map(conflict => conflict.capability);
    const mutualAid = stress.score >= 85
        || mutualAidCapabilities.length >= 3
        ? "EMERGENCY REINFORCEMENT"
        : stress.score >= 65
            || mutualAidCapabilities.length >= 2
            ? "REQUEST MUTUAL AID"
            : stress.score >= 45
                || mutualAidCapabilities.length >= 1
                ? "PREPARE MUTUAL AID"
                : "LOCAL CAPACITY OK";
    const commandChecklist = [
        {
            id: "VERIFY",
            label: "Verify incident intelligence",
            detail: selected.gps_verified
                ? "GPS evidence verified."
                : "Confirm location and available evidence.",
            required: true,
        },
        ...(selected.status === "REPORTED"
            ? [{
                    id: "ACK",
                    label: "Acknowledge incident",
                    detail: "Incident is still waiting for Command acknowledgement.",
                    required: true,
                }]
            : []),
        ...(selectedAssignments.length === 0
            ? [{
                    id: "DISPATCH",
                    label: "Review and dispatch resources",
                    detail: "No backend field assignment exists yet.",
                    required: true,
                }]
            : []),
        ...(selected.analysis.result.hazard_analysis.habitations
            .some(habitation => habitation.risk_level === "RED")
            ? [{
                    id: "REDZONE",
                    label: "Review RED-zone protective action",
                    detail: "Immediate-risk habitation exists.",
                    required: true,
                }]
            : []),
        ...(selected.analysis.result.people_requiring_relocation > 0
            ? [{
                    id: "RELOCATION",
                    label: "Confirm relocation capacity",
                    detail: `${selected.analysis.result.people_requiring_relocation} people require relocation planning.`,
                    required: true,
                }]
            : []),
        ...(selectedAssignments.some(assignment => assignment.status === "ISSUE")
            ? [{
                    id: "ISSUE",
                    label: "Restore or replace failed field capability",
                    detail: "One or more assigned responders report ISSUE.",
                    required: true,
                }]
            : []),
        {
            id: "MONITOR",
            label: "Continue predictive monitoring",
            detail: "Watch route hazards, zone stress and resource demand.",
            required: false,
        },
    ];
    const completedForIncident = completedChecklist[selected.id] ?? [];
    function toggleChecklist(id: string) {
        setCompletedChecklist(current => {
            const existing = current[selected.id] ?? [];
            return {
                ...current,
                [selected.id]: existing.includes(id)
                    ? existing.filter(value => value !== id)
                    : [...existing, id],
            };
        });
    }
    return (<section className="unified-command-module">
      <div className="unified-module-heading">
        <div>
          <span className="truth-badge real">
            INTEGRATED COMMAND WORKSPACE
          </span>

          <h2>{view.replace("_", " ")}</h2>

          <p>
            {selected.incident_type}
            {" / "}
            {selected.location}
            {" · "}
            {selected.fusion_id}
          </p>
        </div>

        <div className="unified-module-status">
          <strong>{selectedPriority}/100</strong>
          <small>DYNAMIC PRIORITY</small>
        </div>
      </div>

      {view === "INTELLIGENCE" && (<>
          <div className="unified-stat-grid">
            <Stat label="FUSION REPORTS" value={String(group.length)}/>
            <Stat label="CHANNELS" value={String(new Set(group.map(report => report.source)).size)}/>
            <Stat label="EVIDENCE QUALITY / 100" value={String(confidence)}/>
            <Stat label="PRIORITY" value={`${selectedPriority}`}/>
          </div>

          <div className="unified-two-column">
            <ModulePanel title="PERSISTENT INCIDENT FUSION" truth="SQLITE fusion_id">
              <Metric label="FUSION ID" value={selected.fusion_id}/>
              <Metric label="SOURCES" value={Array.from(new Set(group.map(report => report.source))).join(" + ")}/>
              <Metric label="RELATED REPORTS" value={String(group.length)}/>

              <div className="unified-list">
                {group.map(report => (<div className="unified-list-row" key={report.id}>
                    <div>
                      <strong>{report.source}</strong>
                      <small>{report.id}</small>
                    </div>
                    <span>{report.status}</span>
                  </div>))}
              </div>
            </ModulePanel>

            <ModulePanel title="GLOBAL PRIORITY QUEUE" truth="SEVERITY + AGE + EXPOSURE">
              {priorityQueue.slice(0, 8).map((item, index) => (<button key={item.report.id} type="button" className={item.report.id === selected.id
                    ? "unified-priority-row selected"
                    : "unified-priority-row"} disabled>
                  <b>#{index + 1}</b>
                  <div>
                    <strong>
                      {item.report.incident_type}
                      {" / "}
                      {item.report.location}
                    </strong>
                    <small>
                      {item.report.status}
                      {" · "}
                      {Math.round(ageMinutes(item.report.created_at))} MIN
                    </small>
                  </div>
                  <span>{item.priority}</span>
                </button>))}
            </ModulePanel>
          </div>

          <div className="unified-two-column">
            <ModulePanel title="NEXT-RISK-ZONE FORECAST" truth="RULE-BASED PREDICTION">
              {zones.length > 0 ? zones.slice(0, 6).map(zone => (<div className="unified-zone-row" key={zone.id}>
                  <div>
                    <strong>{zone.name}</strong>
                    <small>
                      {zone.population} exposed · {zone.priority}
                    </small>
                  </div>
                  <span className={`zone-tone ${zone.forecastLevel.toLowerCase()}`}>
                    {zone.currentScore} → {zone.forecastScore}
                  </span>
                </div>)) : (<Empty>No habitation forecast available.</Empty>)}

              <BackendIntelligence result={selected.analysis.result} />
            </ModulePanel>

            <ModulePanel title="CASCADING-RISK WATCH" truth="RULE-BASED">
              {cascade.map((alert, index) => (<AlertBox key={`${alert.title}-${index}`} level={alert.level} title={alert.title}>
                  {alert.detail}
                </AlertBox>))}
            </ModulePanel>
          </div>
        </>)}

      {view === "FIELD_OPS" && (<>
          <div className="unified-stat-grid">
            <Stat label="OBSERVED" value={String(resourceStates.length)}/>
            <Stat label="AVAILABLE" value={String(freeResources.length)}/>
            <Stat label="BUSY" value={String(resourceStates.filter(resource => resource.state === "BUSY").length)}/>
            <Stat label="ISSUES" value={String(unresolvedIssues.length)}/>
          </div>

          <div className="unified-two-column">
            <ModulePanel title="RESOURCE AVAILABILITY" truth="LIVE ASSIGNMENT STATE">
              {resourceStates.length > 0 ? resourceStates.map(resource => (<Metric key={resource.id} label={`${resource.id} / ${resource.capability}`} value={resource.state} tone={resource.state === "AVAILABLE"
                    ? "good"
                    : resource.state === "ISSUE"
                        ? "danger"
                        : "normal"}/>)) : (<Empty>No resource pool observed yet.</Empty>)}
            </ModulePanel>

            <ModulePanel title="RESOURCE SHORTAGE + BACKUP" truth="REQUIRED VS ACTIVE">
              {shortages.length > 0 ? shortages.map(row => (<div className="unified-shortage-row" key={row.capability}>
                  <Metric label={row.capability} value={`${row.active}/${row.required} ACTIVE`} tone={row.shortage > 0 ? "danger" : "good"}/>
                  <Metric label="SHORTAGE" value={String(row.shortage)} tone={row.shortage > 0 ? "danger" : "good"}/>
                </div>)) : (<Empty>No selected-incident resource requirement.</Empty>)}

              {backupRecommendations.map(row => (<div className="unified-callout" key={`backup-${row.capability}`}>
                  <small>{row.capability} BACKUP</small>
                  <strong>
                    {row.candidates.length > 0
                    ? row.candidates.map(resource => resource.id).join(" + ")
                    : "NO FREE BACKUP IN CURRENT INCIDENT PLAN"}
                  </strong>
                </div>))}
            </ModulePanel>
          </div>

          <div className="unified-two-column">
            <ModulePanel title="LIVE ISSUE QUEUE / REAL REASSIGNMENT" truth="BACKEND SUPPORTED">
              {unresolvedIssues.length > 0 ? unresolvedIssues.map(assignment => {
                const report = reports.find(item => item.id === assignment.report_id);
                return (<div className="unified-issue-card" key={assignment.id}>
                    <small>COMMAND ACTION REQUIRED</small>
                    <strong>{assignment.resource_id}</strong>
                    <span>
                      {report
                        ? `${report.incident_type} / ${report.location}`
                        : assignment.report_id}
                    </span>

                    <button type="button" disabled={reassigning === assignment.id} onClick={() => {
                        void handleReassign(assignment);
                    }}>
                      {reassigning === assignment.id
                        ? "SEARCHING BACKUP..."
                        : "ASSIGN COMPATIBLE BACKUP"}
                    </button>
                  </div>);
            }) : (<Metric label="FIELD STATE" value="NO UNREPLACED ISSUES" tone="good"/>)}

              {actionMessage && (<div className="unified-action-message">
                  {actionMessage}
                </div>)}
            </ModulePanel>

            <ModulePanel title="REPLACEMENT CHAINS" truth="PERSISTENT">
              {replacementAssignments.length > 0 ? replacementAssignments.map(replacement => {
                const old = assignments.find(assignment => assignment.id === replacement.replaces_assignment_id);
                return (<div className="unified-chain" key={replacement.id}>
                    <div>
                      <small>FAILED</small>
                      <strong>
                        {old?.resource_id ?? replacement.replaces_assignment_id}
                      </strong>
                    </div>
                    <b>→</b>
                    <div>
                      <small>REPLACEMENT</small>
                      <strong>{replacement.resource_id}</strong>
                    </div>
                  </div>);
            }) : (<Empty>No backend reassignment chain exists yet.</Empty>)}
            </ModulePanel>
          </div>
        </>)}

      {view === "PREDICTIVE" && (<>
          <div className="unified-stat-grid">
            <Stat label="MAX FORECAST" value={topZone ? String(topZone.forecastScore) : "—"}/>
            <Stat label="PREDICTED RED" value={String(zones.filter(zone => zone.forecastLevel === "RED").length)}/>
            <Stat label="RELOCATION" value={String(selected.analysis.result.people_requiring_relocation)}/>
            <Stat label="ROUTE STRESS" value={String(selectedAssignments.length)}/>
          </div>

          <div className="unified-two-column">
            <ModulePanel title="PREDICTIVE ZONE STRESS" truth="RULE-BASED FORECAST">
              {zones.length > 0 ? zones.map(zone => (<div className="unified-zone-row" key={zone.id}>
                  <div>
                    <strong>{zone.name}</strong>
                    <small>{zone.currentLevel} → {zone.forecastLevel}</small>
                  </div>
                  <span className={`zone-tone ${zone.forecastLevel.toLowerCase()}`}>
                    {zone.currentScore} → {zone.forecastScore}
                  </span>
                </div>)) : (<Empty>No habitation risk data available.</Empty>)}
            </ModulePanel>

            <ModulePanel title="FUTURE RESOURCE DEMAND" truth="DECISION SUPPORT">
              {demandForecast.length > 0 ? demandForecast.map(item => (<div className="unified-shortage-row" key={item.capability}>
                  <Metric label={item.capability} value={`${item.active} ACTIVE`}/>
                  <Metric label="CURRENT → FORECAST" value={`${item.required} → ${item.predictedRequired}`}/>
                  <Metric label="PREDICTED GAP" value={String(item.predictedGap)} tone={item.predictedGap > 0 ? "danger" : "good"}/>
                </div>)) : (<Empty>No resource demand forecast available.</Empty>)}
            </ModulePanel>
          </div>

          <div className="unified-two-column">
            <ModulePanel title="SHELTER FAILURE WHAT-IF" truth="SIMULATION ONLY">
              <ScenarioStressTest key={selected.id+"shelter"} report={selected} mode="shelter" />
            </ModulePanel>

            <ModulePanel title="ROUTE FAILURE WHAT-IF" truth="SIMULATED IMPACT">
              <ScenarioStressTest key={selected.id+"road"} report={selected} mode="road" />
            </ModulePanel>
          </div>
        </>)}

      {view === "COORDINATION" && (<>
          <div className="unified-stat-grid">
            <Stat label="SYSTEM STRESS" value={`${stress.score}`}/>
            <Stat label="READINESS" value={`${readiness.score}%`}/>
            <Stat label="ACTIVE" value={String(stress.active)}/>
            <Stat label="DELAYED" value={String(stress.delayed)}/>
          </div>

          <ModulePanel title="INCIDENT COMPARISON MATRIX" truth="PERSISTED DEMO INCIDENTS">
            <div className="unified-table-wrap">
              <table className="unified-command-table">
                <thead>
                  <tr>
                    <th>INCIDENT</th>
                    <th>STATUS</th>
                    <th>RISK</th>
                    <th>PRIORITY</th>
                    <th>PEOPLE</th>
                    <th>RED</th>
                    <th>RELOCATE</th>
                    <th>UNITS</th>
                  </tr>
                </thead>
                <tbody>
                  {reports
                .filter(report => report.status !== "RESOLVED")
                .map(report => {
                const related = fusionReports(report, reports).length;
                const red = report.analysis.result.hazard_analysis.habitations
                    .filter(habitation => habitation.risk_level === "RED").length;
                const units = assignments.filter(assignment => assignment.report_id === canonicalReportId(report)
                    && assignment.status !== "RESOLVED").length;
                return (<tr key={report.id} className={report.id === selected.id ? "selected" : ""}>
                          <td>
                            <strong>{report.incident_type}</strong>
                            <small>{report.location}</small>
                          </td>
                          <td>{report.status}</td>
                          <td>{report.analysis.result.severity_analysis.risk_score}</td>
                          <td>{priorityScore(report, related)}</td>
                          <td>{report.people_affected}</td>
                          <td>{red}</td>
                          <td>{report.analysis.result.people_requiring_relocation}</td>
                          <td>{units}</td>
                        </tr>);
            })}
                </tbody>
              </table>
            </div>
          </ModulePanel>

          <div className="unified-two-column">
            <ModulePanel title="AGING + PRIORITY ESCALATION" truth="PROTOTYPE SLA WATCH">
              {priorityQueue.slice(0, 8).map((item, index) => {
                const age = ageMinutes(item.report.created_at);
                const state = age >= 45
                    ? "CRITICAL"
                    : age >= 25
                        ? "DELAYED"
                        : age >= 12
                            ? "WATCH"
                            : "NORMAL";
                return (<div className="unified-list-row" key={item.report.id}>
                    <div>
                      <strong>
                        #{index + 1} {item.report.incident_type}
                      </strong>
                      <small>
                        {Math.round(age)} MIN · {state} · {item.report.status}
                      </small>
                    </div>
                    <span>{item.priority}</span>
                  </div>);
            })}
            </ModulePanel>

            <ModulePanel title="MULTI-INCIDENT RESOURCE CONFLICT" truth="CROSS-INCIDENT LOAD">
              {conflicts.length > 0 ? conflicts.map(conflict => (<div className="unified-shortage-row" key={conflict.capability}>
                  <Metric label={conflict.capability} value={`${conflict.active}/${conflict.required} ACTIVE`}/>
                  <Metric label="INCIDENTS DEMANDING" value={String(conflict.incidents)}/>
                  <Metric label="LOAD PRESSURE" value={`${conflict.pressure}%`} tone={conflict.pressure > 110 ? "danger" : "normal"}/>
                </div>)) : (<Metric label="SYSTEM" value="NO CAPABILITY CONFLICT" tone="good"/>)}
            </ModulePanel>
          </div>

          <div className="unified-two-column">
            <ModulePanel title="SYSTEM STRESS + MUTUAL AID" truth="DECISION SUPPORT">
              <Metric label="SYSTEM INDEX" value={`${stress.score}/100 · ${stress.level}`}/>
              <Metric label="SEVERE INCIDENTS" value={String(stress.severe)}/>
              <Metric label="RED-ZONE INCIDENTS" value={String(stress.red)}/>
              <Metric label="FIELD ISSUES" value={String(stress.issues)}/>
              <Metric label="RELOCATION LOAD" value={`${stress.relocation} PEOPLE`}/>

              <div className={mutualAid === "LOCAL CAPACITY OK"
                ? "unified-callout good"
                : "unified-callout warning"}>
                <small>AEGIS RECOMMENDATION</small>
                <strong>{mutualAid}</strong>
                <span>
                  {mutualAidCapabilities.length > 0
                ? `Priority reinforcement: ${mutualAidCapabilities.join(" · ")}`
                : "Current local capacity is adequate."}
                </span>
              </div>
            </ModulePanel>

            <ModulePanel title="OPERATIONAL READINESS" truth="RESOURCE + FIELD + RELOCATION + WORKFLOW">
              <div className="readiness-score">
                <strong>{readiness.score}</strong>
                <span>{readiness.level}</span>
              </div>

              <Metric label="RESOURCE COVERAGE" value={`${readiness.resourceCoverage}%`}/>
              <Metric label="FIELD HEALTH" value={`${readiness.fieldHealth}%`}/>
              <Metric label="RELOCATION READY" value={`${readiness.relocationReadiness}%`}/>
              <Metric label="WORKFLOW PROGRESS" value={`${readiness.workflowProgress}%`}/>
            </ModulePanel>
          </div>

          <div className="unified-two-column">
            <ModulePanel title="COMMAND ACTION CHECKLIST" truth="LOCAL WORKFLOW AID">
              {commandChecklist.map(item => {
                const checked = completedForIncident.includes(item.id);
                return (<button type="button" key={item.id} className={checked
                        ? "unified-check-row checked"
                        : "unified-check-row"} onClick={() => toggleChecklist(item.id)}>
                    <i>{checked ? "✓" : ""}</i>
                    <div>
                      <strong>{item.label}</strong>
                      <small>{item.detail}</small>
                    </div>
                    <span>{item.required ? "REQUIRED" : "MONITOR"}</span>
                  </button>);
            })}
            </ModulePanel>

            <ModulePanel title="LIVE COMMAND / HANDOVER BRIEF" truth="DETERMINISTIC SUMMARY">
              <BriefRow label="SITUATION" value={`${stress.active} active incident(s), ${stress.severe} high-severity, ${stress.red} with RED habitation risk.`}/>
              <BriefRow label="TOP PRIORITY" value={priorityQueue[0]
                ? `${priorityQueue[0].report.incident_type} at ${priorityQueue[0].report.location} · ${priorityQueue[0].priority}/100.`
                : "No active incident."}/>
              <BriefRow label="SELECTED INCIDENT" value={`${selected.status} · ${selected.analysis.result.severity_analysis.severity} · ${selected.analysis.result.severity_analysis.risk_score}/100.`}/>
              <BriefRow label="FIELD" value={`${selectedAssignments.filter(assignment => assignment.status !== "RESOLVED").length} active unit(s), ${selectedAssignments.filter(assignment => assignment.status === "ISSUE").length} ISSUE.`}/>
              <BriefRow label="ACTION" value={mutualAid === "LOCAL CAPACITY OK"
                ? "Continue local coordination and preserve spare response capacity."
                : `${mutualAid}. Review overloaded capabilities before the next dispatch.`} important/>
            </ModulePanel>
          </div>
        </>)}

      {view === "AUDIT" && (<>
          <div className="unified-stat-grid">
            <Stat label="FUSION ID" value={selected.fusion_id.slice(-8)}/>
            <Stat label="EVENTS" value={String(auditEvents.length)}/>
            <Stat label="RESOLVED" value={String(resolved.length)}/>
            <Stat label="DB LINK" value={auditOnline ? "ONLINE" : "OFFLINE"}/>
          </div>

          <div className="unified-two-column">
            <ModulePanel title="PERSISTENT AUDIT TIMELINE" truth="SQLITE audit_events">
              {auditEvents.length > 0 ? auditEvents.map(event => (<div className="audit-event-row" key={event.id}>
                  <small>{timeLabel(event.created_at)}</small>
                  <i />
                  <div>
                    <strong>{event.event_type}</strong>
                    <span>{event.message}</span>
                    <small>
                      {event.actor}
                      {event.assignment_id
                    ? ` · ${event.assignment_id}`
                    : ""}
                    </small>
                  </div>
                </div>)) : (<Empty>No persistent audit events for this fusion group yet.</Empty>)}
            </ModulePanel>

            <ModulePanel title="FUSION HISTORY" truth="PERSISTENT REPORT GROUP">
              <Metric label="FUSION ID" value={selected.fusion_id}/>
              <Metric label="REPORT COUNT" value={String(group.length)}/>
              <Metric label="CHANNELS" value={Array.from(new Set(group.map(report => report.source))).join(" + ")}/>

              {group.map(report => (<div className="unified-list-row" key={report.id}>
                  <div>
                    <strong>{report.source} / {report.incident_type}</strong>
                    <small>{report.id}</small>
                  </div>
                  <span>{report.status}</span>
                </div>))}

              <TruthNote>
                Browser refreshes do not erase fusion IDs, assignment links or audit events.
              </TruthNote>
            </ModulePanel>
          </div>

          <div className="unified-two-column">
            <ModulePanel title="REASSIGNMENT HISTORY" truth="OLD → NEW ASSIGNMENT">
              {replacementAssignments.length > 0 ? replacementAssignments.map(replacement => {
                const old = assignments.find(assignment => assignment.id === replacement.replaces_assignment_id);
                return (<div className="unified-chain" key={replacement.id}>
                    <div>
                      <small>FAILED</small>
                      <strong>{old?.resource_id ?? "UNKNOWN"}</strong>
                    </div>
                    <b>→</b>
                    <div>
                      <small>REPLACEMENT</small>
                      <strong>{replacement.resource_id}</strong>
                    </div>
                  </div>);
            }) : (<Empty>No reassignment history yet.</Empty>)}
            </ModulePanel>

            <ModulePanel title="AFTER-ACTION METRICS" truth="RESOLVED INCIDENTS">
              {resolved.length > 0 ? (<>
                  <div className="unified-stat-grid compact">
                    <Stat label="RESOLVED" value={String(resolved.length)}/>
                    <Stat label="AVG MIN" value={String(Math.round(resolved.reduce((total, item) => total + item.duration, 0) / resolved.length))}/>
                    <Stat label="PEOPLE" value={String(resolved.reduce((total, item) => total + item.report.people_affected, 0))}/>
                    <Stat label="MAX RISK" value={String(Math.max(...resolved.map(item => item.risk)))}/>
                  </div>

                  {resolved.slice(0, 6).map(item => (<div className="unified-list-row" key={item.report.id}>
                      <div>
                        <strong>
                          {item.report.incident_type} / {item.report.location}
                        </strong>
                        <small>{item.units} unit(s)</small>
                      </div>
                      <span>{Math.round(item.duration)} MIN</span>
                    </div>))}
                </>) : (<Empty>Metrics appear after incidents are resolved.</Empty>)}
            </ModulePanel>
          </div>
        </>)}
    </section>);
}
function ModulePanel({ title, truth, children, }: {
    title: string;
    truth: string;
    children: ReactNode;
}) {
    return (<article className="unified-panel">
      <div className="unified-panel-title">
        <strong>{title}</strong>
        <small>{truth}</small>
      </div>
      <div className="unified-panel-body">
        {children}
      </div>
    </article>);
}
function Stat({ label, value, }: {
    label: string;
    value: string;
}) {
    return (<div className="unified-stat">
      <small>{label}</small>
      <strong>{value}</strong>
    </div>);
}
function Metric({ label, value, tone = "normal", }: {
    label: string;
    value: string;
    tone?: "normal" | "good" | "danger";
}) {
    return (<div className="unified-metric">
      <small>{label}</small>
      <strong className={`tone-${tone}`}>{value}</strong>
    </div>);
}
function AlertBox({ level, title, children, }: {
    level: CascadeAlert["level"];
    title: string;
    children: ReactNode;
}) {
    return (<div className={`unified-alert ${level.toLowerCase()}`}>
      <small>{level}</small>
      <strong>{title}</strong>
      <span>{children}</span>
    </div>);
}
function BriefRow({ label, value, important = false, }: {
    label: string;
    value: string;
    important?: boolean;
}) {
    return (<div className={important ? "unified-brief important" : "unified-brief"}>
      <small>{label}</small>
      <span>{value}</span>
    </div>);
}
function TruthNote({ children, }: {
    children: ReactNode;
}) {
    return (<div className="unified-truth-note">
      {children}
    </div>);
}
function Empty({ children, }: {
    children: ReactNode;
}) {
    return (<div className="unified-empty">
      {children}
    </div>);
}
export default UnifiedCommandModules;
