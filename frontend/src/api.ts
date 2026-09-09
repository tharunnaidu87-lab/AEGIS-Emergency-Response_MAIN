// ============================================================
// AEGIS SHARED FRONTEND API
// Public App + Command Center + Responder App
// ============================================================
export const API_BASE = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");
// ============================================================
// BASIC TYPES
// ============================================================
export type EmergencyType = "Flood" | "Landslide" | "Fire" | "Accident";
export type ReportSource = "APP" | "SMS" | "CALL";
export type ReportStatus = "REPORTED" | "ACKNOWLEDGED" | "DISPATCHED" | "EN_ROUTE" | "ON_SCENE" | "RESOLVED";
export type AssignmentStatus = "ASSIGNED" | "ACCEPTED" | "EN_ROUTE" | "ON_SCENE" | "RESOLVED" | "ISSUE";
// ============================================================
// RESOURCE
// ============================================================
export interface ResourceResult {
    capacity?: number;
    eta_minutes?: number;
    selection_reason?: string;
    origin_risk?: string;
    id: string;
    name: string;
    type: string;
    latitude: number;
    longitude: number;
    status: string;
    distance_km: number;
}
// ============================================================
// HABITATION
// ============================================================
export interface HabitationResult {
    habitation_id: string;
    habitation_name: string;
    latitude: number;
    longitude: number;
    distance_from_incident_km: number;
    risk_score: number;
    risk_level: string;
    relocation_priority: string;
    total_population: number;
    estimated_affected_population: number;
    exposure_ratio: number;
    vulnerable_population: {
        children: number;
        elderly: number;
        special_assistance: number;
    };
}
// ============================================================
// RELOCATION
// ============================================================
export interface RelocationAssignment {
    latitude?: number;
    longitude?: number;
    centre_id: string;
    centre_name: string;
    distance_km: number;
    safe_carrying_capacity: number;
    current_occupancy: number;
    available_before_allocation: number;
    people_allocated: number;
    remaining_capacity_after: number;
    limiting_factor: string;
}
// ============================================================
// HOSPITAL
// ============================================================
export interface HospitalResult {
    reason?: string;
    eta_minutes?: number;
    capacity_shortfall?: number;
    id: string;
    name: string;
    latitude: number;
    longitude: number;
    available_beds: number;
    icu_beds: number;
    trauma_center: boolean;
    burn_unit: boolean;
    status: string;
    distance_km: number;
    selection_score: number;
}
// ============================================================
// COMPLETE AEGIS RESULT
// ============================================================
export interface AegisResult {
    confidence_analysis?: { score: number; report_count: number; distinct_evidence_count: number; factors: Record<string, number> };
    priority_analysis?: { score: number; method: string };
    fusion?: { id: string; canonical_report_id: string; report_ids: string[]; report_count: number; population_method: string };
    pipeline?: { stage: string; status: string; duration_ms: number }[];
    prediction?: {
        method: string; horizon_minutes: number; current_radius_km: number; future_radius_km: number;
        future_intensity: number; additional_population_at_risk: number; future_population_requiring_action: number;
        future_resource_requirements: Record<string, number>; assumptions: string;
        habitations: (HabitationResult & { current_risk_score: number; current_risk_level: string })[];
    };
    prepositioning?: { resource_id: string; resource_type: string; zone_id: string; zone_name: string; latitude: number; longitude: number; eta_minutes: number; reason: string; status: string }[];
    population_basis?: string;

    system: string;
    operational_mode: string;
    incident: {
        injured?: number;
        trapped?: number;
        type: string;
        location: string;
        latitude: number;
        longitude: number;
        reported_people_affected: number;
        hazard_intensity: number;
        description: string;
    };
    severity_analysis: {
        factors?: Record<string, number>;
        risk_score: number;
        severity: string;
    };
    resource_plan: {
        spare_resources?: ResourceResult[];
        catalog?: ResourceResult[];
        required_resources: Record<string, number>;
        selected_resources: ResourceResult[];
        shortages: Array<{
            type: string;
            required: number;
            available: number;
            shortage: number;
        }>;
    };
    hospital_plan: {
        selected_hospital: HospitalResult | null;
        alternatives?: unknown[];
        message?: string;
    };
    hazard_analysis: {
        current_radius_km?: number;
        data_coverage?: string;
        total_habitations: number;
        total_population_requiring_action: number;
        priority_summary: {
            immediate_population: number;
            short_term_population: number;
            medium_term_population: number;
        };
        habitations: HabitationResult[];
    };
    people_requiring_relocation: number;
    relocation_plan: {
        people_requiring_relocation: number;
        total_allocated: number;
        unallocated_people: number;
        coverage_percent: number;
        relocation_status: string;
        assignments: RelocationAssignment[];
    } | null;
}
// ============================================================
// AEGIS RESPONSE
// ============================================================
export interface AegisResponse {
    status: string;
    result: AegisResult;
}
// ============================================================
// SHARED REPORT
// ============================================================
export interface SharedReport {
    intake?: IntakeMetadata | null;
    injured?: number;
    trapped?: number;
    id: string;
    fusion_id: string;
    source: ReportSource;
    raw_content: string;
    phone: string;
    incident_type: string;
    location: string;
    latitude: number;
    longitude: number;
    people_affected: number;
    hazard_intensity: number;
    description: string;
    vulnerable_groups: string[];
    gps_verified: boolean;
    spreading: boolean;
    structural_damage: boolean;
    status: ReportStatus;
    analysis: AegisResponse;
    created_at: string;
    updated_at: string;
}
// ============================================================
// RESOURCE ASSIGNMENT
// ============================================================
export interface Assignment {
    departed_at?: string;
    id: string;
    report_id: string;
    resource_id: string;
    resource_name: string;
    resource_type: string;
    start_latitude: number;
    start_longitude: number;
    distance_km: number;
    eta_minutes: number;
    status: AssignmentStatus;
    replaces_assignment_id: string | null;
    replaced_by_assignment_id: string | null;
    assigned_at: string;
    updated_at: string;
}
// ============================================================
// AUDIT EVENT
// ============================================================
export interface AuditEvent {
    id: string;
    report_id: string | null;
    assignment_id: string | null;
    fusion_id: string | null;
    event_type: string;
    actor: string;
    message: string;
    metadata: Record<string, unknown>;
    created_at: string;
}
// ============================================================
// REASSIGNMENT RESPONSE
// ============================================================
export interface ReassignmentResponse {
    status: string;
    original_assignment: Assignment;
    replacement_assignment: Assignment | null;
    already_reassigned: boolean;
    reason: string;
}
// ============================================================
// CREATE REPORT REQUEST
// ============================================================
export interface CreateReportRequest {
    intake_unknown_fields?: IntakeUnknownField[];
    injured?: number;
    trapped?: number;
    source: ReportSource;
    raw_content: string;
    phone: string;
    incident_type: string;
    location: string;
    latitude: number;
    longitude: number;
    people_affected: number;
    hazard_intensity: number;
    description: string;
    vulnerable_groups: string[];
    gps_verified: boolean;
    spreading: boolean;
    structural_damage: boolean;
}
// ============================================================
// DIRECT ANALYSIS REQUEST
// ============================================================
export interface AnalysisRequest {
    report_id?: string;
    vulnerable_groups?: string[];
    gps_verified?: boolean;
    spreading?: boolean;
    structural_damage?: boolean;
    scenario?: ScenarioOptions;

    injured?: number;
    trapped?: number;
    incident_type: string;
    location: string;
    latitude: number;
    longitude: number;
    people_affected: number;
    hazard_intensity: number;
    description: string;
}
// ============================================================
// GENERIC FETCH
// ============================================================
async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, { ...options, signal: options?.signal ?? AbortSignal.timeout(12000) });
    if (!response.ok) {
        let message = `AEGIS backend error ${response.status}`;
        try {
            const body = await response.json();
            if (body.detail) {
                message =
                    typeof body.detail ===
                        "string"
                        ? body.detail
                        : JSON.stringify(body.detail);
            }
        }
        catch {
            // Response was not JSON.
        }
        throw new Error(message);
    }
    const data: T = await response.json();
    return data;
}

export type IntakeUnknownField = 'people_affected' | 'injured' | 'trapped' | 'spreading' | 'structural_damage';
export interface IntakeExtraction {
    source: 'SMS' | 'CALL';
    method: 'LOCAL_RULE_BASED';
    incident_type: EmergencyType | null;
    location: string | null;
    people_affected: number | null;
    injured: number | null;
    trapped: number | null;
    vulnerable_groups: string[];
    spreading: boolean | null;
    structural_damage: boolean | null;
    hazard_intensity: number;
    hazard_basis: string;
    description: string;
    latitude: number | null;
    longitude: number | null;
    gps_verified: boolean;
    confidence: number;
    confidence_factors: Record<string, number>;
    missing_fields: string[];
    questions: string[];
    warnings: string[];
    evidence: Record<string, string>;
}
export interface IntakeMetadata {
    extraction: IntakeExtraction;
    reviewed: Record<string, string | number | boolean | string[] | null>;
    unknown_fields: IntakeUnknownField[];
    corrected_fields: string[];
    confidence_basis: string;
}
export function parseIntake(input: { source: 'SMS' | 'CALL'; text: string; latitude?: number; longitude?: number; gps_verified: boolean }, signal: AbortSignal) {
    // Render cold starts may exceed the normal operational polling timeout.
    return apiFetch<IntakeExtraction>('/intake/parse', { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
        signal: AbortSignal.any([signal, AbortSignal.timeout(60000)]) });
}
// ============================================================
// HEALTH
// ============================================================
export async function checkBackend() {
    return apiFetch<{
        status: string;
        backend: string;
        database: string;
    }>("/health");
}
// ============================================================
// DIRECT AEGIS ANALYSIS
// ============================================================
export async function runAegisAnalysis(report: AnalysisRequest) {
    return apiFetch<AegisResponse>("/aegis-analyse", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(report),
    });
}
// ============================================================
// CREATE REPORT
// ============================================================
export async function submitReport(report: CreateReportRequest) {
    return apiFetch<{
        status: string;
        fusion_id: string;
        report: SharedReport;
    }>("/reports", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(report),
    });
}
// ============================================================
// LIST REPORTS
// ============================================================
export async function listReports() {
    const response = await apiFetch<{
        status: string;
        total: number;
        reports: SharedReport[];
    }>("/reports");
    return response.reports;
}
// ============================================================
// GET REPORT
// ============================================================
export async function getReport(reportId: string) {
    const response = await apiFetch<{
        status: string;
        report: SharedReport;
    }>(`/reports/${encodeURIComponent(reportId)}`);
    return response.report;
}
// ============================================================
// PERSISTENT FUSION GROUP
// ============================================================
export async function getFusionReports(fusionId: string) {
    const response = await apiFetch<{
        status: string;
        fusion_id: string;
        total: number;
        reports: SharedReport[];
    }>(`/fusion/${encodeURIComponent(fusionId)}/reports`);
    return response.reports;
}
// ============================================================
// UPDATE REPORT STATUS
// ============================================================
export async function updateReportStatus(reportId: string, status: ReportStatus) {
    const response = await apiFetch<{
        status: string;
        report: SharedReport;
    }>(`/reports/${encodeURIComponent(reportId)}/status`, {
        method: "PATCH",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            status,
        }),
    });
    return response.report;
}
// ============================================================
// DISPATCH
// ============================================================
export async function dispatchReport(reportId: string) {
    return apiFetch<{
        status: string;
        report: SharedReport;
        assignments: Assignment[];
    }>(`/reports/${encodeURIComponent(reportId)}/dispatch`, {
        method: "POST",
    });
}
// ============================================================
// LIST ASSIGNMENTS
// ============================================================
export async function listAssignments(resourceId?: string, reportId?: string) {
    const query = new URLSearchParams();
    if (resourceId) {
        query.set("resource_id", resourceId);
    }
    if (reportId) {
        query.set("report_id", reportId);
    }
    const queryString = query.toString();
    const path = queryString
        ? `/assignments?${queryString}`
        : "/assignments";
    const response = await apiFetch<{
        status: string;
        total: number;
        assignments: Assignment[];
    }>(path);
    return response.assignments;
}
// ============================================================
// UPDATE ASSIGNMENT STATUS
// ============================================================
export async function updateAssignmentStatus(assignmentId: string, status: AssignmentStatus) {
    const response = await apiFetch<{
        status: string;
        assignment: Assignment;
    }>(`/assignments/${encodeURIComponent(assignmentId)}/status`, {
        method: "PATCH",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            status,
        }),
    });
    return response.assignment;
}
// ============================================================
// REAL BACKUP / REASSIGNMENT
// ============================================================
export async function reassignAssignment(assignmentId: string, reason = "UNIT_ISSUE") {
    return apiFetch<ReassignmentResponse>(`/assignments/${encodeURIComponent(assignmentId)}/reassign`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            reason,
        }),
    });
}
// ============================================================
// AUDIT HISTORY
// ============================================================
export async function listAuditEvents(filters?: {
    reportId?: string;
    assignmentId?: string;
    fusionId?: string;
    limit?: number;
}) {
    const query = new URLSearchParams();
    if (filters?.reportId) {
        query.set("report_id", filters.reportId);
    }
    if (filters?.assignmentId) {
        query.set("assignment_id", filters.assignmentId);
    }
    if (filters?.fusionId) {
        query.set("fusion_id", filters.fusionId);
    }
    if (filters?.limit) {
        query.set("limit", String(filters.limit));
    }
    const queryString = query.toString();
    const path = queryString
        ? `/audit-events?${queryString}`
        : "/audit-events";
    const response = await apiFetch<{
        status: string;
        total: number;
        events: AuditEvent[];
    }>(path);
    return response.events;
}
// ============================================================
// RELOCATION CENTRES
// ============================================================
export async function getRelocationCentres() {
    return apiFetch<{
        status: string;
        total_centres: number;
        centres: unknown[];
    }>("/relocation-centres");
}

export interface ScenarioOptions {
    unavailable_resource_ids?: string[];
    closed_shelter_ids?: string[];
    hospital_capacity_factor?: number;
    shelter_capacity_factor?: number;
    road_blocked?: boolean;
    response_delay_minutes?: number;
    forecast_minutes?: number;
}

export function canonicalReportId(report: SharedReport) {
    return report.analysis.result.fusion?.canonical_report_id ?? report.id;
}
