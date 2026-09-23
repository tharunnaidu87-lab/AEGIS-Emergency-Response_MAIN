import ReportPhotos from "./ReportPhotos";
import PhotoPicker from "./PhotoPicker";
import { SosButton, QueuedReceipt } from "./DeliveryUI";
import { queueReport } from "./outbox";
import DistressPanel from "./DistressPanel";
import IncidentLifecycle from "./IncidentLifecycle";
import { useRoadScenario } from "./useRoadScenario";
import { useEffect, useMemo, useState, useCallback, lazy, Suspense, } from "react";
import { BrowserRouter, Link, Navigate, Route, Routes, useNavigate, useParams, useSearchParams, } from "react-router-dom";
import "./App.css";
import { useRoadRoutes, assessRoadScenario, movementProgress } from "./routing";
import { usePolling } from "./usePolling";
import { canonicalReportId } from "./api";
import IntakeChannels from "./IntakeChannels";
import IntakeMethodSelector from "./IntakeMethodSelector";
import IntakeReportDetails from "./IntakeReportDetails";
import BackendIntelligence from "./BackendIntelligence";
const OperationalMap = lazy(() => import("./OperationalMap"));
import { dispatchReport, getReport, listAssignments, listReports, runAegisAnalysis, updateAssignmentStatus, type AegisResponse, type Assignment, type AssignmentStatus, type EmergencyType, type ReportStatus, type SharedReport, } from "./api";
import UnifiedCommandModules, { type UnifiedCommandView, } from "./UnifiedCommandModules";
// ============================================================
// CONSTANTS
// ============================================================
const INCIDENT_TYPES: EmergencyType[] = [
    "Flood",
    "Landslide",
    "Fire",
    "Accident",
];
const REPORT_STAGES: ReportStatus[] = [
    "REPORTED",
    "DISPATCHED",
    "EN_ROUTE",
    "ON_SCENE",
    "RESOLVED",
];
const RESPONDER_STATUSES: AssignmentStatus[] = [
    "ACCEPTED",
    "EN_ROUTE",
    "ON_SCENE",
    "RESOLVED",
    "ISSUE",
];
type CommandView = "OVERVIEW" | UnifiedCommandView | "WHAT_IF" | "RELOCATION";
const COMMAND_VIEWS: Array<{
    id: CommandView;
    code: string;
    label: string;
}> = [
    { id: "OVERVIEW", code: "01", label: "OVERVIEW" },
    { id: "INTELLIGENCE", code: "02", label: "ASSESSMENT" },
    { id: "FIELD_OPS", code: "03", label: "FIELD OPS" },
    { id: "PREDICTIVE", code: "04", label: "PROJECTIONS" },
    { id: "COORDINATION", code: "05", label: "COORDINATION" },
    { id: "WHAT_IF", code: "06", label: "SCENARIOS" },
    { id: "RELOCATION", code: "07", label: "RELOCATION" },
    { id: "AUDIT", code: "08", label: "AUDIT" },
];
// ============================================================
// HOSPITAL DISPLAY TYPES
// ============================================================
type UnknownRecord = Record<string, unknown>;
type HospitalDisplay = {
    id: string;
    name: string;
    distanceKm: number | null;
    availableBeds: number | null;
    icuBeds: number | null;
    status: string;
    reason: string;
    latitude: number | null;
    longitude: number | null;
    specialties: string[];
};
// ============================================================
// RISK MAP TYPES
// ============================================================
function App() {
    return (<BrowserRouter>

      <Routes>
        <Route path="/queued/:localId" element={<QueuedReceipt />} />
        <Route path="/sms" element={<IntakeChannels source="SMS" />} />
        <Route path="/call" element={<IntakeChannels source="CALL" />} />
        <Route path="*" element={<main className="center-state"><h1>Page not found</h1><Link to="/report">OPEN AEGIS</Link></main>} />

        <Route path="/" element={<Navigate to="/report" replace/>}/>


        <Route path="/report" element={<ReportPage />}/>


        <Route path="/track/:reportId" element={<TrackPage />}/>


        <Route path="/command" element={<CommandPage />}/>


        <Route path="/responder" element={<ResponderPage />}/>


        <Route path="/simulate" element={<Navigate to="/command" replace/>}/>


        <Route path="/relocation" element={<Navigate to="/command" replace/>}/>

      </Routes>

    </BrowserRouter>);
}
// ============================================================
// HEADERS
// ============================================================
function PublicHeader() {
    return (<nav className="top-nav">

      <Link to="/report" className="brand">

        <span className="brand-mark">
          <i />
          <i />
          <i />
        </span>


        <span className="brand-copy">

          <strong>
            AEGIS
          </strong>

          <small>
            EMERGENCY REPORTING
          </small>

        </span>


        <span className="brand-code">
          PUBLIC//01
        </span>

      </Link>


      <span className="demo-node">
        <i />
        PUBLIC REPORTING DEMO
      </span>

    </nav>);
}
function CommandHeader() {
    return (<nav className="top-nav">

      <Link to="/command" className="brand">

        <span className="brand-mark">
          <i />
          <i />
          <i />
        </span>


        <span className="brand-copy">

          <strong>
            AEGIS
          </strong>

          <small>
            UNIFIED EMERGENCY OPERATIONS
          </small>

        </span>


        <span className="brand-code">
          CONTROL//01
        </span>

      </Link>


      <span className="demo-node">
        <i />
        COMMAND CENTER DEMO
      </span>

    </nav>);
}
function ResponderHeader({ unitId, }: {
    unitId: string;
}) {
    return (<nav className="top-nav">

      <div className="brand">

        <span className="brand-mark">
          <i />
          <i />
          <i />
        </span>


        <span className="brand-copy">

          <strong>
            AEGIS FIELD
          </strong>

          <small>
            FIELD RESPONSE OPERATIONS
          </small>

        </span>


        <span className="brand-code">
          {unitId}
        </span>

      </div>


      <span className="demo-node">
        <i />
        RESPONDER DEMO
      </span>

    </nav>);
}
// ============================================================
// GENERAL HELPERS
// ============================================================
function formatTime(value: string) {
    return new Date(value).toLocaleString();
}
function publicReportStatus(status: ReportStatus) {
    if (status === "REPORTED" || status === "ACKNOWLEDGED") return "AWAITING AUTHORITY APPROVAL";
    return status.replaceAll("_", " ");
}
function publicReportStageIndex(status: ReportStatus) {
    if (status === "ACKNOWLEDGED") return 0;
    return Math.max(0, REPORT_STAGES.indexOf(status));
}
function distanceKm(lat1: number, lon1: number, lat2: number, lon2: number) {
    const radius = 6371;
    const radians = (value: number) => value *
        Math.PI /
        180;
    const dLat = radians(lat2 -
        lat1);
    const dLon = radians(lon2 -
        lon1);
    const a = Math.sin(dLat /
        2) ** 2
        +
            Math.cos(radians(lat1))
                *
                    Math.cos(radians(lat2))
                *
                    Math.sin(dLon /
                        2) ** 2;
    return (radius *
        2 *
        Math.atan2(Math.sqrt(a), Math.sqrt(1 -
            a)));
}
function asRecord(value: unknown): UnknownRecord | null {
    if (typeof value !==
        "object"
        ||
            value ===
                null
        ||
            Array.isArray(value)) {
        return null;
    }
    return value as UnknownRecord;
}
function readString(record: UnknownRecord | null, keys: string[]) {
    if (!record) {
        return "";
    }
    for (const key of keys) {
        const value = record[key];
        if (typeof value ===
            "string"
            &&
                value.trim()) {
            return value;
        }
    }
    return "";
}
function readNumber(record: UnknownRecord | null, keys: string[]): number | null {
    if (!record) {
        return null;
    }
    for (const key of keys) {
        const value = record[key];
        if (typeof value ===
            "number"
            &&
                Number.isFinite(value)) {
            return value;
        }
        if (typeof value ===
            "string"
            &&
                value.trim()) {
            const parsed = Number(value);
            if (Number.isFinite(parsed)) {
                return parsed;
            }
        }
    }
    return null;
}
function readStringArray(record: UnknownRecord | null, keys: string[]) {
    if (!record) {
        return [];
    }
    for (const key of keys) {
        const value = record[key];
        if (Array.isArray(value)) {
            return value
                .filter(item => typeof item ===
                "string")
                .map(item => String(item));
        }
    }
    return [];
}
// ============================================================
// FEATURE 1
// HOSPITAL INTELLIGENCE
// ============================================================
function extractHospital(hospitalPlan: unknown): HospitalDisplay | null {
    if (hospitalPlan ===
        null
        ||
            hospitalPlan ===
                undefined) {
        return null;
    }
    let candidate: unknown = hospitalPlan;
    if (Array.isArray(hospitalPlan)) {
        candidate =
            hospitalPlan[0];
    }
    else {
        const plan = asRecord(hospitalPlan);
        if (plan) {
            const objectKeys = [
                "selected_hospital",
                "recommended_hospital",
                "hospital",
                "primary_hospital",
                "best_hospital",
            ];
            for (const key of objectKeys) {
                if (asRecord(plan[key])) {
                    candidate =
                        plan[key];
                    break;
                }
            }
            const arrayKeys = [
                "hospitals",
                "recommended_hospitals",
                "ranked_hospitals",
                "selected_hospitals",
            ];
            for (const key of arrayKeys) {
                const value = plan[key];
                if (Array.isArray(value)
                    &&
                        value.length >
                            0) {
                    candidate =
                        value[0];
                    break;
                }
            }
        }
    }
    const hospital = asRecord(candidate);
    if (!hospital) {
        return null;
    }
    const capacity = asRecord(hospital.capacity);
    const id = readString(hospital, [
        "id",
        "hospital_id",
        "code",
    ])
        ||
            "HOSPITAL";
    const name = readString(hospital, [
        "name",
        "hospital_name",
        "centre_name",
    ])
        ||
            id;
    const distanceKmValue = readNumber(hospital, [
        "distance_km",
        "distance",
        "distanceKm",
    ]);
    const availableBeds = readNumber(hospital, [
        "available_beds",
        "beds_available",
        "available_capacity",
        "free_beds",
    ])
        ??
            readNumber(capacity, [
                "available",
                "available_beds",
                "free",
            ]);
    const icuBeds = readNumber(hospital, [
        "icu_available",
        "icu_beds_available",
        "icu_free",
    ])
        ??
            readNumber(capacity, [
                "icuFree",
                "icu_free",
                "icu_available",
            ]);
    const status = readString(hospital, [
        "status",
        "availability",
        "capacity_status",
    ])
        ||
            (availableBeds !==
                null
                ? availableBeds >
                    0
                    ? "AVAILABLE"
                    : "FULL"
                : "AEGIS SELECTED");
    const reason = readString(hospital, [
        "reason",
        "selection_reason",
        "recommendation_reason",
        "why_selected",
    ])
        ||
            "Selected by the AEGIS hospital recommendation engine.";
    const latitude = readNumber(hospital, [
        "latitude",
        "lat",
    ]);
    const longitude = readNumber(hospital, [
        "longitude",
        "lng",
        "lon",
    ]);
    const specialties = readStringArray(hospital, [
        "specialties",
        "specialisations",
        "specializations",
        "capabilities",
    ]);
    return {
        id,
        name,
        distanceKm: distanceKmValue,
        availableBeds,
        icuBeds,
        status: status.toUpperCase(),
        reason,
        latitude,
        longitude,
        specialties,
    };
}
// ============================================================
// FEATURE 2
// RED-ZONE MAP INTELLIGENCE
// ============================================================
function ReportPage() {
    const navigate = useNavigate();
    const [incidentType, setIncidentType] = useState<EmergencyType>("Flood");
    const [injured, setInjured] = useState(0);
    const [trapped, setTrapped] = useState(0);
    const [phone, setPhone] = useState("");
    const [people, setPeople] = useState(0);
    const [photos, setPhotos] = useState<string[]>([]);
    const [location, setLocation] = useState("");
    const [latitude, setLatitude] = useState("");
    const [longitude, setLongitude] = useState("");
    const [hazardIntensity, setHazardIntensity] = useState(0.8);
    const [description, setDescription] = useState("");
    const [gpsVerified, setGpsVerified] = useState(false);
    const [spreading, setSpreading] = useState(false);
    const [structuralDamage, setStructuralDamage] = useState(false);
    const [vulnerableGroups, setVulnerableGroups] = useState<string[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    function toggleVulnerable(group: string) {
        setVulnerableGroups(current => current.includes(group)
            ? current.filter(item => item !==
                group)
            : [
                ...current,
                group,
            ]);
    }
    function useGps() {
        setError("");
        if (!navigator.geolocation) {
            setError("GPS is unavailable on this device.");
            return;
        }
        navigator
            .geolocation
            .getCurrentPosition(position => {
            setLatitude(position
                .coords
                .latitude
                .toFixed(6));
            setLongitude(position
                .coords
                .longitude
                .toFixed(6));
            setGpsVerified(true);
            setLocation(current => current.trim()
                ? current
                : "GPS verified location");
        }, () => {
            setError("Unable to obtain device location.");
        });
    }
    async function sendReport() {
        setError("");
        if (!location.trim()) {
            setError("Enter the emergency location.");
            return;
        }
        if (!description.trim()) {
            setError("Describe what is happening.");
            return;
        }
        if (Math.max(injured, trapped) > people) { setError("Injured/trapped counts cannot exceed people affected."); return; }
        const lat = Number(latitude);
        const lng = Number(longitude);
        if (!latitude.trim() || !longitude.trim() || Math.abs(lat) > 90 || Math.abs(lng) > 180 || !Number.isFinite(lat)
            ||
                !Number.isFinite(lng)) {
            setError("Invalid coordinates.");
            return;
        }
        setLoading(true);
        try {
            const localId = await queueReport({
                photos,
                source: "APP",
                injured, trapped,
                raw_content: description,
                phone,
                incident_type: incidentType,
                location,
                latitude: lat,
                longitude: lng,
                people_affected: people,
                hazard_intensity: hazardIntensity,
                description,
                vulnerable_groups: vulnerableGroups,
                gps_verified: gpsVerified,
                spreading,
                structural_damage: structuralDamage,
            });
            navigate(`/queued/${localId}`);
        }
        catch (submitError) {
            console.error(submitError);
            setError(submitError instanceof Error ? submitError.message : "AEGIS could not submit the emergency report.");
        }
        finally {
            setLoading(false);
        }
    }
    return (<div className="aegis-shell">

      <PublicHeader />


      <main className="citizen-page">

        <IntakeMethodSelector active="APP" />
        <SosButton />

        <section className="citizen-intro">

          <div className="hero-reference">
            AEGIS / PUBLIC INTAKE
          </div>


          <h1>
            Report an emergency.
          </h1>


          <p>
            Share what happened, who is at risk,
            and where help is needed. AEGIS will
            assess the report for this local
            command demonstration.
          </p>

        </section>


        <PhotoPicker photos={photos} onChange={setPhotos} />
        <section className="report-board">
          <button className="demo-fill" type="button" onClick={() => { setIncidentType("Flood"); setLocation("Riverbank Village, Chennai"); setLatitude("13.1300"); setLongitude("80.2200"); setPeople(18); setInjured(3); setTrapped(4); setHazardIntensity(0.8); setDescription("Flood water is entering riverbank homes. People are trapped and water is spreading toward nearby streets."); setSpreading(true); setVulnerableGroups(["Children", "Elderly"]); setGpsVerified(false); }}>LOAD FLOOD DEMO</button>


          <div className="report-step">

            <span className="step-number">
              01
            </span>


            <div>

              <small>
                INCIDENT TYPE
              </small>

              <h2>
                What happened?
              </h2>

            </div>

          </div>


          <div className="incident-choice-grid">

            {INCIDENT_TYPES.map(type => (<button key={type} type="button" className={incidentType ===
                type
                ? "incident-choice active"
                : "incident-choice"} onClick={() => setIncidentType(type)}>

                  <span>

                    {type
                .slice(0, 3)
                .toUpperCase()}

                  </span>


                  <strong>
                    {type}
                  </strong>

                </button>))}

          </div>


          <div className="report-step">

            <span className="step-number">
              02
            </span>


            <div>

              <small>
                PEOPLE AT RISK
              </small>

              <h2>
                Who needs help?
              </h2>

            </div>

          </div>


          <div className="form-grid">

            <label>

              People affected

              <input type="number" min="1" value={people} onChange={event => setPeople(Math.max(1, Number(event.target.value)
            ||
                1))}/>

            </label>


            <label>

              Contact number

              <input value={phone} placeholder="Optional" onChange={event => setPhone(event.target.value)}/>

            </label>

          </div>


          <div className="form-grid"><label>Injured people<input aria-label="Injured people" type="number" min="0" max={people} value={injured} onChange={e => setInjured(Math.max(0, Number(e.target.value)))} /></label><label>Trapped people<input aria-label="Trapped people" type="number" min="0" max={people} value={trapped} onChange={e => setTrapped(Math.max(0, Number(e.target.value)))} /></label></div>
<div className="chip-grid">

            {[
            "Children",
            "Elderly",
            "Disabled",
            "Medical dependent",
        ].map(group => (<button key={group} type="button" className={vulnerableGroups.includes(group)
                ? "selection-chip active"
                : "selection-chip"} onClick={() => toggleVulnerable(group)}>
                  {group}
                </button>))}

          </div>


          <div className="report-step">

            <span className="step-number">
              03
            </span>


            <div>

              <small>
                LOCATION
              </small>

              <h2>
                Where is the emergency?
              </h2>

            </div>

          </div>


          <button type="button" className="gps-button" onClick={useGps}>

            <span>
              USE CURRENT LOCATION
            </span>


            <strong>

              {gpsVerified
            ? "GPS VERIFIED"
            : "LOCATE"}

            </strong>

          </button>


          <label className="full-field">

            Location or landmark

            <input value={location} placeholder="Road, bridge, village, building..." onChange={event => setLocation(event.target.value)}/>

          </label>


          <div className="form-grid">

            <label>

              Latitude

              <input value={latitude} onChange={event => { setLatitude(event.target.value); setGpsVerified(false); }}/>

            </label>


            <label>

              Longitude

              <input value={longitude} onChange={event => { setLongitude(event.target.value); setGpsVerified(false); }}/>

            </label>

          </div>


          <div className="report-step">

            <span className="step-number">
              04
            </span>


            <div>

              <small>
                INCIDENT DETAILS
              </small>

              <h2>
                What is happening?
              </h2>

            </div>

          </div>


          <label className="full-field">

            Emergency description

            <textarea value={description} placeholder="Example: Water is entering houses and people are trapped..." onChange={event => setDescription(event.target.value)}/>

          </label>


          <label className="intensity-field">

            Hazard intensity

            <span>

              {Math.round(hazardIntensity *
            100)}

              %

            </span>


            <input type="range" min="0.1" max="1" step="0.05" value={hazardIntensity} onChange={event => setHazardIntensity(Number(event.target.value))}/>

          </label>


          <div className="chip-grid">

            <button type="button" className={spreading
            ? "selection-chip active"
            : "selection-chip"} onClick={() => setSpreading(current => !current)}>
              Situation spreading
            </button>


            <button type="button" className={structuralDamage
            ? "selection-chip active"
            : "selection-chip"} onClick={() => setStructuralDamage(current => !current)}>
              Structural damage
            </button>

          </div>


          {error && (<div className="form-alert">
              {error}
            </div>)}


          <button type="button" className="citizen-submit" disabled={loading} onClick={() => {
            void sendReport();
        }}>

            {loading
            ? "AEGIS PROCESSING..."
            : "REPORT EMERGENCY"}

          </button>


          <div className="prototype-notice">

            DEMONSTRATION SYSTEM —
            NOT CONNECTED TO OFFICIAL
            EMERGENCY DISPATCH.

          </div>

        </section>

      </main>

    </div>);
}
// ============================================================
// TRACKING
// ============================================================
function TrackPage() {
    const { reportId } = useParams();
    const read = useCallback(async () => reportId ? getReport(reportId) : null, [reportId]);
    const { data: report, error } = usePolling(read, null as SharedReport | null, 3000);
    if (error && !report) {
        return (<div className="aegis-shell">

        <PublicHeader />


        <main className="center-state">

          <h1>
            {error}
          </h1>

        </main>

      </div>);
    }
    if (!report) {
        return (<div className="aegis-shell">

        <PublicHeader />


        <main className="center-state">

          <h1>
            Loading report status...
          </h1>

        </main>

      </div>);
    }
    const currentIndex = publicReportStageIndex(report.status);
    return (<div className="aegis-shell">

      <PublicHeader />


      <main className="receipt-layout">

        <section className="citizen-receipt">

          <div className="receipt-status-line">

            <span className="receipt-check">
              ✓
            </span>

            <span>
              AEGIS PUBLIC INTAKE
            </span>

            <span>
              {publicReportStatus(report.status)}
            </span>

          </div>


          <div className="receipt-title-block">

            <p>
              Keep this reference number.
            </p>


            <h1>
              {report.id}
            </h1>


            <span>
              Your report has been received
              for AEGIS Command review.
            </span>

          </div>


          <div className="receipt-facts">

            <div>

              <span>
                Incident
              </span>

              <strong>
                {report.incident_type}
              </strong>

            </div>


            <div>

              <span>
                Risk assessment
              </span>

              <strong>

                {report
            .analysis
            .result
            .severity_analysis
            .severity}

                {" · "}

                {report
            .analysis
            .result
            .severity_analysis
            .risk_score}

                /100

              </strong>

            </div>


            <div>

              <span>
                Location
              </span>

              <strong>
                {report.location}
              </strong>

            </div>


            <div>

              <span>
                Last updated
              </span>

              <strong>
                {formatTime(report.updated_at)}
              </strong>

            </div>

          </div>


          <div className="receipt-progress">

            {REPORT_STAGES.map((stage, index) => (<span key={stage} className={index <=
                currentIndex
                ? "progress-step active"
                : "progress-step"}>
                  {stage === "REPORTED" ? "REPORT RECEIVED" : stage.replaceAll("_", " ")}
                </span>))}

          </div>


          <div className="receipt-actions">
            <div className="citizen-primary-action track-live-status" role="status">STATUS UPDATES APPEAR ABOVE</div>


            <Link className="citizen-primary-action" to="/report">
              REPORT ANOTHER EMERGENCY
            </Link>

          </div>

        </section>

      </main>

    </div>);
}
// ============================================================
// HOSPITAL PANEL
// ============================================================
function HospitalIntelligence({ response, }: {
    response: AegisResponse;
}) {
    const hospital = extractHospital(response
        .result
        .hospital_plan);
    if (!hospital) {
        return (<section className="risk-board reveal">

        <div className="ops-panel-title">

          <span>
            HOSPITAL CAPACITY ASSESSMENT
          </span>

          <small>
            RULE-BASED RECOMMENDATION
          </small>

        </div>


        <div className="empty-module">
          No suitable hospital recommendation
          is available for this incident.
        </div>

      </section>);
    }
    return (<section className="risk-board reveal">

      <div className="ops-panel-title">

        <span>
          HOSPITAL CAPACITY ASSESSMENT
        </span>

        <small>
          RULE-BASED RECOMMENDATION
        </small>

      </div>


      <div style={{
            display: "grid",
            gridTemplateColumns: "minmax(220px,1.4fr) repeat(3,minmax(100px,1fr))",
            border: "1px solid #35403d",
            background: "rgba(15,20,19,.75)",
        }}>

        <div style={{
            padding: 16,
            borderRight: "1px solid #35403d",
        }}>

          <span className="truth-badge rule">
            RECOMMENDED
          </span>


          <h3 style={{
            margin: "10px 0 5px",
            fontSize: 17,
        }}>
            {hospital.name}
          </h3>


          <small>
            {hospital.id}
          </small>


          <p style={{
            marginTop: 12,
            marginBottom: 0,
            lineHeight: 1.55,
            color: "#a6aeaa",
            fontSize: 10,
        }}>
            {hospital.reason}
          </p>

        </div>


        <div style={{
            padding: 16,
        }}>

          <small>
            DISTANCE
          </small>


          <strong style={{
            display: "block",
            marginTop: 8,
            fontSize: 18,
        }}>

            {hospital.distanceKm !==
            null
            ? `${hospital.distanceKm.toFixed(1)} KM`
            : "N/A"}

          </strong>

        </div>


        <div style={{
            padding: 16,
        }}>

          <small>
            BEDS AVAILABLE
          </small>


          <strong style={{
            display: "block",
            marginTop: 8,
            fontSize: 18,
        }}>

            {hospital.availableBeds ??
            "N/A"}

          </strong>


          {hospital.icuBeds !==
            null && (<small style={{
                display: "block",
                marginTop: 6,
            }}>
              ICU AVAILABLE{" "}
              {hospital.icuBeds}
            </small>)}

        </div>


        <div style={{
            padding: 16,
        }}>

          <small>
            STATUS
          </small>


          <strong style={{
            display: "block",
            marginTop: 8,
            fontSize: 14,
        }}>
            {hospital.status}
          </strong>


          {hospital.specialties.length >
            0 && (<small style={{
                display: "block",
                marginTop: 7,
            }}>

              {hospital.specialties
                .slice(0, 3)
                .join(" · ")}

            </small>)}

        </div>

      </div>


      <div style={{
            marginTop: 8,
            display: "flex",
            gap: 7,
            flexWrap: "wrap",
        }}>

        <span className="truth-badge rule">
          RULE-BASED SELECTION
        </span>


        {hospital.latitude !==
            null
            &&
                hospital.longitude !==
                    null && (<span className="truth-badge real">
            HOSPITAL GPS ON MAP
          </span>)}

      </div>

    </section>);
}
// ============================================================
// COMMAND CENTER
// ============================================================
function CommandPage() {
    const [search, setSearch] = useSearchParams();
    const selectedId = search.get("report") || "";
    const setSelectedId = (id: string) => setSearch({ report: id });
    const read = useCallback(async () => {
        const [reports, assignments] = await Promise.all([listReports(), listAssignments()]);
        if (selectedId && !reports.some(r => r.id === selectedId)) reports.push(await getReport(selectedId));
        return { reports, assignments };
    }, [selectedId]);
    const { data, error: backendError, loading: commandLoading, refresh: refreshCommand } = usePolling(read, { reports: [] as SharedReport[], assignments: [] as Assignment[] });
    const { reports, assignments } = data;
    const backendOnline = !commandLoading && !backendError;
    const original = reports.find(report => report.id === selectedId);
    // Each report keeps its submitted observation. Command uses the fused incident estimate.
    const selected = useMemo(() => original ? { ...original,
        people_affected: original.analysis.result.incident.reported_people_affected,
        hazard_intensity: original.analysis.result.incident.hazard_intensity,
        latitude: original.analysis.result.incident.latitude,
        longitude: original.analysis.result.incident.longitude,
        injured: original.analysis.result.incident.injured ?? original.injured,
        trapped: original.analysis.result.incident.trapped ?? original.trapped,
    } : undefined, [original]);
    const [commandRoadBlocked] = useRoadScenario(selected?.fusion_id);
    const selectedAssignments = useMemo(() => selected ? assignments.filter(a => a.report_id === canonicalReportId(selected) && !a.replaced_by_assignment_id) : [], [selected, assignments]);
    const [revealStage, setRevealStage] = useState(0);
    const [commandView, setCommandView] = useState<CommandView>("OVERVIEW");
    const [simulationIntensity, setSimulationIntensity] = useState(0);
    const [simulationPeople, setSimulationPeople] = useState(0);
    const [shelterFactor, setShelterFactor] = useState(1);
    const [hospitalFactor, setHospitalFactor] = useState(1);
    const [unavailableUnit, setUnavailableUnit] = useState("");
    const [roadBlocked, setRoadBlocked] = useState(false);
    const [simulation, setSimulation] = useState<AegisResponse | null>(null);
    const [simulationLoading, setSimulationLoading] = useState(false);
    const [simulationError, setSimulationError] = useState("");
    const [actionError, setActionError] = useState("");
    const [actionBusy, setActionBusy] = useState(false);
    const { routes: commandRoutes, status: commandRoutingStatus } = useRoadRoutes(selected, selectedAssignments);
    const baselinePeople = selected?.people_affected ?? 0;
    const baselineIntensity = selected?.hazard_intensity ?? 0;
    useEffect(() => {
        const initialize = requestAnimationFrame(() => {
        setRevealStage(0);
        setSimulationPeople(baselinePeople);
        setSimulationIntensity(baselineIntensity);
        setSimulation(null); setSimulationError(""); setActionError("");
        setShelterFactor(1); setHospitalFactor(1); setUnavailableUnit(""); setRoadBlocked(false);
        setCommandView("OVERVIEW");
        });
        if (!selectedId) return () => cancelAnimationFrame(initialize);
        // Replay stored backend stages; computation completed before the report receipt.
        const timers = [1,2,3,4,5,6,7].map(stage => setTimeout(() => setRevealStage(stage), stage * 140));
        return () => { cancelAnimationFrame(initialize); timers.forEach(clearTimeout); };
    }, [selectedId, baselinePeople, baselineIntensity]);
    async function commandAction(action: () => Promise<unknown>) {
        setActionBusy(true); setActionError("");
        try { await action(); await refreshCommand(); }
        catch (error) { setActionError(error instanceof Error ? error.message : "Command action failed."); }
        finally { setActionBusy(false); }
    }
async function dispatch() {
        if (selected) await commandAction(() => dispatchReport(selected.id));
    }
    async function startMovement() {
        await commandAction(async () => {
            const outcomes = await Promise.allSettled(selectedAssignments.filter(a => ["ASSIGNED", "ACCEPTED"].includes(a.status)).map(a => updateAssignmentStatus(a.id, "EN_ROUTE")));
            const failed = outcomes.find(result => result.status === "rejected");
            if (failed?.status === "rejected") throw failed.reason;
        });
    }
    async function runWhatIf() {
        if (!selected) return;
        setSimulationLoading(true); setSimulationError("");
        try {
            const response = await runAegisAnalysis({
                report_id: selected.id, incident_type: selected.incident_type, location: selected.location,
                latitude: selected.latitude, longitude: selected.longitude, people_affected: simulationPeople,
                hazard_intensity: simulationIntensity, description: selected.description,
                injured: Math.min(simulationPeople, selected.injured ?? 0), trapped: Math.min(simulationPeople, selected.trapped ?? 0),
                vulnerable_groups: selected.vulnerable_groups, gps_verified: selected.gps_verified,
                spreading: selected.spreading, structural_damage: selected.structural_damage,
                scenario: { shelter_capacity_factor: shelterFactor, hospital_capacity_factor: hospitalFactor,
                    unavailable_resource_ids: unavailableUnit ? [unavailableUnit] : [], road_blocked: roadBlocked },
            });
            setSimulation(response);
        } catch (error) { setSimulationError(error instanceof Error ? error.message : "Scenario calculation failed."); }
        finally { setSimulationLoading(false); }
    }
    if (!selected) {
        return (<div className="aegis-shell">

        <DistressPanel /><CommandHeader />


        <main className="command-empty">

          <section className="command-empty-core">

            <span className="truth-badge real">

              {backendOnline
                ? "BACKEND ONLINE"
                : "BACKEND OFFLINE"}

            </span>


            <div className="command-id">
              OPS / STANDBY
            </div>


            <h1>
              AEGIS COMMAND CENTER
            </h1>


            <p>
              {selectedId ? (commandLoading ? "Loading selected report..." : "Selected report is unavailable.") : "Standing by. Submit a report or select a saved incident to begin."}
            </p>


            {backendError && <p className="form-alert" role="alert">{backendError}</p>}
            <Link className="citizen-primary-action" to="/report">OPEN REPORTER PORTAL</Link>
            <div className="saved-incidents">{reports.map(r => <button key={r.id} onClick={() => setSelectedId(r.id)}>{r.incident_type} · {r.location} · {r.id}</button>)}</div>
            <div className="waiting-sequence">

              <span>
                WAIT
              </span>

              <i />

              <span>
                RECEIVE
              </span>

              <i />

              <span>
                UNDERSTAND
              </span>

              <i />

              <span>
                PRIORITIZE
              </span>

              <i />

              <span>
                DISPATCH
              </span>

              <i />

              <span>
                RELOCATE
              </span>

            </div>

          </section>


          <section className="intake-status-board">

            <h2>
              INTAKE CHANNEL STATUS
            </h2>


            <div className="channel-card live">

              <span>
                APP
              </span>

              <strong>
                ACTIVE
              </strong>

              <small>
                Online form intake
              </small>

            </div>


            <div className="channel-card">

              <span>
                SMS
              </span>

              <strong>
                LOCAL DEMO ADAPTER
              </strong>

              <small>
                Rule-based text interpretation
              </small>

            </div>


            <div className="channel-card">

              <span>
                CALL
              </span>

              <strong>
                LOCAL DEMO ADAPTER
              </strong>

              <small>
                Voice transcript intake
              </small>

            </div>

          </section>

        </main>

      </div>);
    }
    const result = selected
        .analysis
        .result;
    const unifiedView: UnifiedCommandView | null = commandView === "INTELLIGENCE"
        || commandView === "FIELD_OPS"
        || commandView === "PREDICTIVE"
        || commandView === "COORDINATION"
        || commandView === "AUDIT"
        ? commandView
        : null;
    return (<div className="aegis-shell">

      <DistressPanel /><CommandHeader />


      <main className="command-layout">
        <div className="command-notices">
          {backendError && <p className="form-alert" role="alert">Connection interrupted: {backendError}. Showing last successful snapshot.</p>}
          {actionError && <p className="form-alert" role="alert">{actionError}</p>}
        </div>

        <aside className="incident-rail">

          <div className="rail-title">

            <small>
              INCOMING REPORTS
            </small>

            <strong>
              {reports.length}
            </strong>

          </div>


          {reports.map(report => (<button key={report.id} type="button" className={selected.id ===
                report.id
                ? "incident-ticket selected"
                : "incident-ticket"} onClick={() => setSelectedId(report.id)}>

                <div className="ticket-head">

                  <span>
                    {report.source}
                  </span>

                  <small>

                    {new Date(report.created_at).toLocaleTimeString()}

                  </small>

                </div>


                <strong>
                  {report.incident_type}
                </strong>


                <p>
                  {report.location}
                </p>


                <div className="ticket-score">

                  <span>

                    {report
                .analysis
                .result
                .severity_analysis
                .severity}

                  </span>


                  <b>

                    {report
                .analysis
                .result
                .severity_analysis
                .risk_score}

                  </b>

                </div>

              </button>))}

        </aside>


        <section className="command-workspace">


          <div className="incident-command-header">

            <div>

              <span className="truth-badge real">

                {selected.source}

                {" / REPORT RECEIVED"}

              </span>


              <h1>

                {selected.incident_type}

                {" / "}

                {selected.location}

              </h1>


              <p>

                {selected.id}

                {" · FUSION "}

                {selected.fusion_id}

                {" · "}

                {publicReportStatus(selected.status)}

              </p>

            </div>


            <div className="command-status">

              <i />

              {publicReportStatus(selected.status)}

            </div>

          </div>


          <IncidentLifecycle
            report={selected}
            assignments={selectedAssignments}
            audience="COMMAND"
          />


                    <details className="pipeline-receipt" open={revealStage < 7}><summary><strong>BACKEND ANALYSIS RECEIVED</strong><span>{revealStage < 7 ? "Presenting calculation stages..." : "Calculation results ready"}</span></summary>
            <div>{(selected.analysis.result.pipeline || []).slice(0, Math.ceil(revealStage * 10 / 7)).map(stage => <span key={stage.stage}>{stage.stage} | {stage.duration_ms.toFixed(1)} ms</span>)}</div>
          </details>
          {revealStage >= 2 && <BackendIntelligence result={selected.analysis.result} condensed />}
          {original && <><ReportPhotos reportId={original.id} /><IntakeReportDetails report={original} /></>}

<div className="command-module-tabs">

            {COMMAND_VIEWS.map(item => (<button key={item.id} type="button" className={commandView ===
                item.id
                ? "active"
                : ""} onClick={() => setCommandView(item.id)}>
                  <small>
                    {item.code}
                  </small>

                  {item.label}

                  {item.id ===
                "RELOCATION"
                &&
                    result
                        .people_requiring_relocation >
                        0 && (<span className="module-alert">

                      {result
                    .people_requiring_relocation}

                    </span>)}

                  {item.id ===
                "AUDIT"
                &&
                    selected.fusion_id && (<span className="module-dot"/>)}

                </button>))}

          </div>


          {commandView ===
            "OVERVIEW" && (<>

              <section className={revealStage >=
                2
                ? "analysis-strip reveal"
                : "analysis-strip"}>

                <div>

                  <small>
                    SOURCE
                  </small>

                  <strong>
                    {selected.source}
                  </strong>

                </div>


                <div>

                  <small>
                    GPS
                  </small>

                  <strong>

                    {selected.gps_verified
                ? "VERIFIED"
                : "PROVIDED"}

                  </strong>

                </div>


                <div>

                  <small>
                    PEOPLE
                  </small>

                  <strong>
                    {selected.people_affected}
                  </strong>

                </div>


                <div>

                  <small>
                    STATUS
                  </small>

                  <strong>
                    {publicReportStatus(selected.status)}
                  </strong>

                </div>

              </section>


              <section className={revealStage >=
                3
                ? "map-stage reveal"
                : "map-stage"}>

                <div className="map-stage-header">

                  <span>
                    GEOSPATIAL OVERVIEW
                  </span>


                  <div className="map-stage-status">

                    <span className="truth-badge real">
                      {commandRoutingStatus.startsWith("OSRM") ? "OSRM ROUTES" : "ESTIMATED ROUTING"}
                    </span>


                    <span className="truth-badge rule">
                      HAZARD ZONE ASSESSMENT
                    </span>


                    <span className="truth-badge rule">
                      ROUTE SCENARIO
                    </span>

                  </div>

                </div>


                <Suspense fallback={<div className="map-loading">Loading operational map...</div>}><OperationalMap report={selected} assignments={selectedAssignments} routeSets={commandRoutes} routingStatus={commandRoutingStatus}/></Suspense>

              </section>


              <section className={revealStage >=
                4
                ? "intelligence-grid reveal"
                : "intelligence-grid"}>

                <div className="intel-card priority">

                  <small>
                    SEVERITY
                  </small>

                  <strong>

                    {result
                .severity_analysis
                .severity}

                  </strong>

                  <span>

                    {result
                .severity_analysis
                .risk_score}

                    /100

                  </span>

                </div>


                <div className="intel-card">

                  <small>
                    MODE
                  </small>

                  <strong className="small-value">

                    {result
                .operational_mode}

                  </strong>

                </div>


                <div className="intel-card">

                  <small>
                    RELOCATION
                  </small>

                  <strong>

                    {result
                .people_requiring_relocation}

                  </strong>

                  <span>
                    PEOPLE
                  </span>

                </div>


                <div className="intel-card">

                  <small>
                    ASSIGNMENTS
                  </small>

                  <strong>
                    {selectedAssignments.length}
                  </strong>

                  <span>
                    FIELD UNITS
                  </span>

                </div>

              </section>


              <section className={revealStage >=
                5
                ? "operations-columns reveal"
                : "operations-columns"}>

                <article className="ops-panel">

                  <div className="ops-panel-title">

                    <span>
                      RESOURCE ALLOCATION
                    </span>

                    <small>
                      RULE-BASED PLAN
                    </small>

                  </div>


                  {result
                .resource_plan
                .selected_resources
                .map(resource => (<div key={resource.id} className="resource-row" title={resource.selection_reason}>

                          <div>

                            <strong>
                              {resource.id}
                            </strong>

                            <small>
                              {resource.type}
                            </small>

                          </div>


                          <span>

                            {resource.distance_km}

                            {" km"}

                          </span>

                        </div>))}


                 <div className="status-buttons">

  <button
  type="button"
  className="dispatch-button"
  disabled={
    actionBusy ||
    selected.status === "RESOLVED" ||
    selectedAssignments.length > 0
  }
  onClick={() => {
    void dispatch();
  }}
>
  {selectedAssignments.length > 0
    ? "RESPONSE DISPATCHED"
    : actionBusy
      ? "APPROVING RESPONSE..."
      : "APPROVE & DISPATCH RESPONSE"}
</button>

  <button
    type="button"
    className="dispatch-button"
    disabled={
      actionBusy ||
      !selectedAssignments.some(a =>
        ["ASSIGNED", "ACCEPTED"].includes(a.status)
      ) ||
      !Object.keys(commandRoutes).length
    }
    onClick={() => {
      void startMovement();
    }}
  >
    START SIMULATED MOVEMENT
  </button>
  </div>

                </article>


                <article className="ops-panel">

                  <div className="ops-panel-title">

                    <span>
                      FIELD RESPONSE OPERATIONS
                    </span>

                    <small>
                      ASSIGNMENT STATUS
                    </small>

                  </div>


                  {selectedAssignments.length >
                0
                ? selectedAssignments.map(assignment => {
                    const routes = commandRoutes[assignment.resource_id]
                        ??
                            [];
                    const assessment = assessRoadScenario(routes, commandRoadBlocked);
                    const decision = { recommendedIndex: assessment.index, rerouted: assessment.index > 0 };
                    const route = routes[decision.recommendedIndex]
                        ??
                            routes[0];
                    const eta = route
                        ? Math.max(1, Math.round(route.duration /
                            60))
                        : assignment
                            .eta_minutes;
                    return (<div key={assignment.id} className="resource-row">

                              <div>

                                <strong>

                                  {assignment
                            .resource_id}

                                </strong>


                                <small>

                                  {assignment
                            .status}


                                  {decision.rerouted
                            ? " · REROUTED"
                            : ""}

                                </small>

                              </div>


                              <span>

                                ETA{" "}

                                {eta}

                                {" min"}

                              </span>

                            </div>);
                })
                : (<div className="empty-module">
                        Awaiting authority approval and dispatch.
                      </div>)}

                </article>

              </section>


              {revealStage >=
                5 && (<HospitalIntelligence response={selected.analysis}/>)}


              <section className={revealStage >=
                6
                ? "risk-board reveal"
                : "risk-board"}>

                <div className="ops-panel-title">

                  <span>
                    HABITATION RISK ASSESSMENT
                  </span>

                  <small>
                    SHOWN ON GEOSPATIAL OVERVIEW
                  </small>

                </div>


                <div className="risk-list">

                  {result
                .hazard_analysis
                .habitations
                .map(habitation => (<div key={habitation
                    .habitation_id} className={`risk-row risk-${habitation
                    .risk_level
                    .toLowerCase()}`}>

                          <div>

                            <strong>

                              {habitation
                    .habitation_name}

                            </strong>


                            <small>

                              {habitation
                    .relocation_priority}

                            </small>

                          </div>


                          <span>

                            {habitation
                    .risk_level}

                            {" · "}

                            {habitation
                    .risk_score}

                          </span>


                          <b>

                            {habitation
                    .estimated_affected_population}

                            {" exposed"}

                          </b>

                        </div>))}

                </div>

              </section>


              <section className={revealStage >=
                7
                ? "relocation-command reveal"
                : "relocation-command"}>

                <div className="ops-panel-title">

                  <span>
                    RELOCATION READINESS
                  </span>

                  <small>
                    SHELTER CAPACITY
                  </small>

                </div>


                {result.relocation_plan
                ? (<>

                      <div className="relocation-summary">

                        <div>

                          <small>
                            REQUIRED
                          </small>

                          <strong>

                            {result
                        .relocation_plan
                        .people_requiring_relocation}

                          </strong>

                        </div>


                        <div>

                          <small>
                            ALLOCATED
                          </small>

                          <strong>

                            {result
                        .relocation_plan
                        .total_allocated}

                          </strong>

                        </div>


                        <div>

                          <small>
                            REMAINING
                          </small>

                          <strong>

                            {result
                        .relocation_plan
                        .unallocated_people}

                          </strong>

                        </div>


                        <div>

                          <small>
                            COVERAGE
                          </small>

                          <strong>

                            {result
                        .relocation_plan
                        .coverage_percent}

                            %

                          </strong>

                        </div>

                      </div>


                      <button type="button" className="open-command-module" onClick={() => setCommandView("RELOCATION")}>
                        OPEN RELOCATION PLAN
                      </button>

                    </>)
                : (<div className="empty-module">
                      No relocation action required.
                    </div>)}

              </section>

            </>)}


          {unifiedView && (<UnifiedCommandModules view={unifiedView} selected={selected} reports={reports} assignments={assignments} onRefresh={refreshCommand}/>)}


          {commandView ===
            "WHAT_IF" && (<section className="integrated-command-module">

              <div className="integrated-module-heading">

                <div>

                  <span className="truth-badge rule">
                    RULE-BASED RECALCULATION
                  </span>


                  <h2>
                    Response Scenario Analysis
                  </h2>


                  <p>
                    Compare planning assumptions
                    without changing the active
                    incident or dispatch records.
                  </p>

                </div>


                <div className="simulation-safety">

                  <strong>
                    SIMULATION ONLY
                  </strong>

                  <small>
                    ACTIVE INCIDENT WILL NOT CHANGE
                  </small>

                </div>

              </div>


              <div className="integrated-whatif-grid">

                <article className="scenario-controls">

                  <div className="ops-panel-title">

                    <span>
                      SCENARIO INPUT
                    </span>

                    <small>
                      SELECTED INCIDENT
                    </small>

                  </div>


                  <label>

                    Hazard intensity

                    <strong>

                      {Math.round(simulationIntensity *
                100)}

                      %

                    </strong>


                    <input type="range" min="0.1" max="1" step="0.05" value={simulationIntensity} onChange={event => { setSimulationIntensity(Number(event.target.value)); setSimulation(null); }}/>

                  </label>


                  <label>

                    People affected

                    <strong>
                      {simulationPeople}
                    </strong>


                    <input type="number" min="1" value={simulationPeople} onChange={event => { setSimulationPeople(Math.max(1, Number(event.target.value) || 1)); setSimulation(null); }}/>

                  </label>


                  <label>Shelter capacity retained: {Math.round(shelterFactor * 100)}%<input aria-label="Shelter capacity retained" type="range" min="0" max="1" step="0.1" value={shelterFactor} onChange={e => { setShelterFactor(Number(e.target.value)); setSimulation(null); }} /></label>
                  <label>Hospital capacity retained: {Math.round(hospitalFactor * 100)}%<input aria-label="Hospital capacity retained" type="range" min="0" max="1" step="0.1" value={hospitalFactor} onChange={e => { setHospitalFactor(Number(e.target.value)); setSimulation(null); }} /></label>
                  <label>Unavailable unit<select aria-label="Unavailable unit" value={unavailableUnit} onChange={e => { setUnavailableUnit(e.target.value); setSimulation(null); }}><option value="">All baseline units available</option>{(result.resource_plan.catalog || result.resource_plan.selected_resources).map(r => <option key={r.id} value={r.id}>{r.id}</option>)}</select></label>
                  <label className="scenario-checkbox"><input type="checkbox" checked={roadBlocked} onChange={e => { setRoadBlocked(e.target.checked); setSimulation(null); }} />Simulated road disruption (+50% estimated travel)</label>
                  <button type="button" className="scenario-run" disabled={simulationLoading} onClick={() => {
                void runWhatIf();
            }}>
                    {simulationLoading
                ? "AEGIS RECALCULATING..."
                : "RUN SCENARIO ANALYSIS"}
                  </button>


                  {simulationError && (<div className="form-alert">
                      {simulationError}
                    </div>)}

                </article>


                <ScenarioResult title="CURRENT ASSESSMENT" response={selected.analysis}/>


                <ScenarioResult title="SCENARIO ASSESSMENT" response={simulation}/>

              </div>

            </section>)}


          {commandView ===
            "RELOCATION" && (<section className="integrated-command-module">

              <div className="integrated-module-heading">

                <div>

                  <span className="truth-badge simulated">
                    RISK ASSESSMENT
                  </span>


                  <h2>
                    Relocation Planning
                  </h2>


                  <p>
                    Habitation exposure, response
                    priority, and shelter-capacity
                    allocation.
                  </p>

                </div>


                <div className="simulation-safety relocation-warning">

                  <strong>

                    {result
                .people_requiring_relocation}

                    {" PEOPLE"}

                  </strong>

                  <small>
                    REQUIRE RELOCATION
                  </small>

                </div>

              </div>


              <div className="command-relocation-grid">

                <article className="command-risk-column">

                  <div className="ops-panel-title">

                    <span>
                      HABITATIONS
                    </span>

                    <small>
                      PRIORITY ORDER
                    </small>

                  </div>


                  {result
                .hazard_analysis
                .habitations
                .map(habitation => (<div key={habitation
                    .habitation_id} className={`zone-card risk-${habitation
                    .risk_level
                    .toLowerCase()}`}>

                          <strong>

                            {habitation
                    .habitation_name}

                          </strong>


                          <span>

                            {habitation
                    .risk_level}

                            {" · "}

                            {habitation
                    .risk_score}

                            /100

                          </span>


                          <small>

                            {habitation
                    .relocation_priority}

                            {" · "}

                            {habitation
                    .estimated_affected_population}

                            {" exposed"}

                          </small>

                        </div>))}

                </article>


                <article className="command-relocation-main">

                  <div className="ops-panel-title">

                    <span>
                      POPULATION ALLOCATION
                    </span>

                    <small>
                      SHELTER CAPACITY
                    </small>

                  </div>


                  {result.relocation_plan
                ? (<>

                        <div className="relocation-summary">

                          <div>

                            <small>
                              AT RISK
                            </small>

                            <strong>

                              {result
                        .relocation_plan
                        .people_requiring_relocation}

                            </strong>

                          </div>


                          <div>

                            <small>
                              ALLOCATED
                            </small>

                            <strong>

                              {result
                        .relocation_plan
                        .total_allocated}

                            </strong>

                          </div>


                          <div>

                            <small>
                              UNALLOCATED
                            </small>

                            <strong>

                              {result
                        .relocation_plan
                        .unallocated_people}

                            </strong>

                          </div>


                          <div>

                            <small>
                              COVERAGE
                            </small>

                            <strong>

                              {result
                        .relocation_plan
                        .coverage_percent}

                              %

                            </strong>

                          </div>

                        </div>


                        <div className="shelter-ranking">

                          {result
                        .relocation_plan
                        .assignments
                        .map((assignment, index) => (<div key={assignment
                            .centre_id} className="shelter-card">

                                  <div>

                                    <small>

                                      {index ===
                            0
                            ? "PRIMARY CENTRE"
                            : "SECONDARY CENTRE"}

                                    </small>


                                    <strong>

                                      {assignment
                            .centre_name}

                                    </strong>

                                  </div>


                                  <span>

                                    {assignment
                            .people_allocated}

                                    {" PEOPLE"}

                                  </span>


                                  <small>

                                    Remaining capacity:{" "}

                                    {assignment
                            .remaining_capacity_after}

                                    {" · "}

                                    {assignment
                            .limiting_factor}

                                  </small>

                                </div>))}

                        </div>

                      </>)
                : (<div className="empty-module">

                        Current AEGIS analysis
                        does not require relocation.

                      </div>)}

                </article>

              </div>

            </section>)}

        </section>

      </main>

    </div>);
}
// ============================================================
// WHAT-IF RESULT
// ============================================================
function ScenarioResult({ title, response, }: {
    title: string;
    response: AegisResponse | null;
}) {
    if (!response) {
        return (<section className="scenario-result empty">

        <small>
          {title}
        </small>

        <strong>
          Waiting.
        </strong>

      </section>);
    }
    const result = response.result;
    return (<section className="scenario-result">

      <small>
        {title}
      </small>


      <div>

        <span>
          Severity
        </span>

        <strong>

          {result
            .severity_analysis
            .severity}

        </strong>

      </div>


      <div>

        <span>
          Risk
        </span>

        <strong>

          {result
            .severity_analysis
            .risk_score}

        </strong>

      </div>


      <div>

        <span>
          Relocation
        </span>

        <strong>

          {result
            .people_requiring_relocation}

        </strong>

      </div>


      <div>

        <span>
          Coverage
        </span>

        <strong>

          {result
            .relocation_plan
            ?.coverage_percent
            ??
                100}

          %

        </strong>

      </div>

      <div><span>Selected hospital</span><strong>{result.hospital_plan.selected_hospital?.name || "No safe hospital available"}</strong></div>
      <div><span>Allocated / Unallocated</span><strong>{result.relocation_plan?.total_allocated ?? 0} / {result.relocation_plan?.unallocated_people ?? 0}</strong></div>
      <div><span>Projected hazard radius</span><strong>{result.prediction?.future_radius_km.toFixed(2) ?? "Unavailable"} km</strong></div>
      <div><span>Response units</span><strong>{result.resource_plan.selected_resources.map(r => r.id).join(", ") || "No compatible available units"}</strong></div>
      <div><span>Staging recommendations</span><strong>{result.prepositioning?.map(r => r.resource_id).join(", ") || "None"}</strong></div>
    </section>);
}
// ============================================================
// RESPONDER RULES
// ============================================================
function responderStatusAllowed(current: AssignmentStatus, next: AssignmentStatus) {
    if (next ===
        "ISSUE") {
        return (current ===
            "ASSIGNED"
            ||
                current ===
                    "ACCEPTED"
            ||
                current ===
                    "EN_ROUTE"
            ||
                current ===
                    "ON_SCENE");
    }
    if (current ===
        "ASSIGNED") {
        return next ===
            "ACCEPTED";
    }
    if (current ===
        "ACCEPTED") {
        return next ===
            "EN_ROUTE";
    }
    if (current === "EN_ROUTE") return next === "ON_SCENE";
    if (current ===
        "ON_SCENE") {
        return next ===
            "RESOLVED";
    }
    return false;
}
// ============================================================
// RESPONDER
// ============================================================
function ResponderPage() {
    const parameters = new URLSearchParams(window.location.search);
    const unitId = sessionStorage.getItem("aegis_unit") || parameters.get("unit")
        ||
            "AMB-02";
    const read = useCallback(async () => {
        const assignments = await listAssignments(unitId);
        const reports: SharedReport[] = [];
        for (const assignment of assignments.filter(a => a.status !== "RESOLVED")) {
            if (!reports.some(r => r.id === assignment.report_id)) reports.push(await getReport(assignment.report_id));
        }
        return { assignments, reports };
    }, [unitId]);
    const { data, error: responderError, loading: responderLoading, refresh: refreshResponder } = usePolling(read, { assignments: [] as Assignment[], reports: [] as SharedReport[] });
    const { assignments, reports } = data;
    const [actionError, setActionError] = useState("");
    const current = assignments.find(assignment => assignment.status !==
        "RESOLVED"
        &&
            assignment.status !==
                "ISSUE");
    const issueAssignment = !current
        ? assignments.find(assignment => assignment.status ===
            "ISSUE")
        : undefined;
    const currentReport = current
        ? reports.find(report => report.id ===
            current.report_id)
        : undefined;
    const [responderRoadBlocked] = useRoadScenario(currentReport?.fusion_id);
    const [navigationClock, setNavigationClock] = useState(Date.now);
    useEffect(() => {
        if (current?.status !== "EN_ROUTE") return;
        const timer = window.setInterval(() => setNavigationClock(Date.now()), 1000);
        return () => window.clearInterval(timer);
    }, [current?.status]);
    const currentAssignments = current
        ? [
            current
        ]
        : [];
    const { routes: responderRoutes, status: responderRoutingStatus, } = useRoadRoutes(currentReport, currentAssignments);
    const nearby = useMemo(() => {
        if (!current
            ||
                !currentReport) {
            return [];
        }
        return reports
            .filter(report => {
            if (report.id ===
                currentReport.id
                ||
                    report.status ===
                        "RESOLVED") {
                return false;
            }
            const required = report
                .analysis
                .result
                .resource_plan
                .required_resources[current.resource_type]
                ??
                    0;
            return required >
                0;
        })
            .map(report => ({
            report,
            distance: distanceKm(current.start_latitude, current.start_longitude, report.latitude, report.longitude),
        }))
            .sort((first, second) => first.distance -
            second.distance)
            .slice(0, 5);
    }, [
        current,
        currentReport,
        reports,
    ]);
    async function changeStatus(status: AssignmentStatus) {
        if (!current) {
            return;
        }
        if (!responderStatusAllowed(current.status, status)) {
            setActionError(`Invalid transition: ${current.status} → ${status}`);
            return;
        }
        setActionError("");
        try {
            await updateAssignmentStatus(current.id, status);
            await refreshResponder();
        }
        catch (error) {
            console.error(error);
            setActionError(error instanceof Error ? error.message : "AEGIS could not update responder status.");
        }
    }
    if (!current) {
        return (<div className="aegis-shell">

        <ResponderHeader unitId={unitId}/>


        <main className="center-state">

          {issueAssignment
                ? (<>

                <h1>
                  UNIT REQUIRES ATTENTION
                </h1>

                <p>
                  Issue reported to
                  AEGIS Command.
                </p>

                <div className="truth-badge simulated">
                  ISSUE REPORTED TO COMMAND
                </div>

              </>)
                : (<>

                <h1>{responderLoading ? "CONNECTING TO COMMAND" : responderError ? "CONNECTION UNAVAILABLE" : "AWAITING ASSIGNMENT"}</h1>

                <p>
                  {responderError || "No active assignment from Command Center."}
                </p>

                <div className="truth-badge real">
                  READY FOR DISPATCH
                </div>

              </>)}

        </main>

      </div>);
    }
    if (!currentReport) {
        return (<div className="aegis-shell">

        <ResponderHeader unitId={unitId}/>


        <main className="center-state">

          <h1>
            MISSION DATA ERROR
          </h1>

        </main>

      </div>);
    }
    const routes = responderRoutes[current.resource_id]
        ??
            [];
    const assessment = assessRoadScenario(routes, responderRoadBlocked);
    const decision = { recommendedIndex: assessment.index, rerouted: assessment.index > 0, reason: assessment.reason };
    const roadRoute = routes[decision.recommendedIndex]
        ??
            routes[0];
    const journeyProgress = current.status === "ON_SCENE" ? 1 :
        roadRoute ? movementProgress(current, roadRoute, navigationClock) : 0;
    const roadEta = Math.ceil((roadRoute ? roadRoute.duration / 60 : current.eta_minutes) * (1 - journeyProgress));
    const roadDistance = ((roadRoute ? roadRoute.distance / 1000 : current.distance_km) * (1 - journeyProgress)).toFixed(1);
    return (<div className="aegis-shell">

      <ResponderHeader unitId={unitId}/>


      <main className="responder-layout">
        {responderError && <p className="form-alert" role="alert">{responderError}. Last known mission is shown.</p>}

        <section className="responder-device">

          <div className="responder-device-head">

            <span>
              CURRENT MISSION
            </span>

            <strong>
              {current.status}
            </strong>

          </div>


          <div className="responder-unit">

            <small>
              ASSIGNED UNIT
            </small>

            <h1>
              {current.resource_id}
            </h1>

          </div>


          <IncidentLifecycle
            report={currentReport}
            assignments={currentAssignments}
            audience="RESPONDER"
            compact
          />


          <div className="assignment-card">

            <span>
              INCIDENT
            </span>

            <strong>
              {currentReport.incident_type}
            </strong>


            <span>
              LOCATION
            </span>

            <strong>
              {currentReport.location}
            </strong>


            <span>
              PRIORITY
            </span>

            <strong>

              {currentReport
            .analysis
            .result
            .severity_analysis
            .severity}

            </strong>


            <span>
              REMAINING ETA
            </span>

            <strong>

              {roadEta}

              {" MIN"}

            </strong>


            <span>
              REMAINING DISTANCE
            </span>

            <strong>

              {roadDistance}

              {" KM"}

            </strong>


            <span>
              PEOPLE
            </span>

            <strong>
              {currentReport.analysis.result.incident.reported_people_affected}
            </strong>


            <span>
              REPORTER NOTE
            </span>

            <strong>
              {currentReport.description}
            </strong>

          </div>


          <div className="map-stage reveal">

            <div className="map-stage-header">

              <span>
                RESPONDER NAVIGATION
              </span>


              <div className="map-stage-status">

                <span className="truth-badge real">
                  {roadRoute?.source === "OSRM" ? "OSRM ROUTE" : "ESTIMATED ROUTING"}
                </span>


                <span className="truth-badge rule">
                  ROAD SCENARIO
                </span>

              </div>

            </div>


            <Suspense fallback={<div className="map-loading">Loading operational map...</div>}><OperationalMap report={currentReport} assignments={[
            current
        ]} routeSets={responderRoutes} routingStatus={responderRoutingStatus} focusUnitId={current.resource_id} compact/></Suspense>

          </div>


          {actionError && (<div className="form-alert">
              {actionError}
            </div>)}


          <div className="status-buttons">

            {RESPONDER_STATUSES.map(status => {
            const allowed = responderStatusAllowed(current.status, status);
            return (<button key={status} type="button" disabled={!allowed} className={current.status ===
                    status
                    ? "active"
                    : ""} onClick={() => {
                    void changeStatus(status);
                }}>

                    {status ===
                    "ON_SCENE"
                    ? "ON SCENE"
                    : status.replace("_", " ")}

                  </button>);
        })}

          </div>


          <div className="prototype-notice">

            RESPONDERS ACT ONLY ON ASSIGNED INCIDENTS.
            ROUTE GUIDANCE IS FOR THIS DEMONSTRATION.

          </div>


          <div className="risk-board reveal">

            <div className="ops-panel-title">

              <span>
                NEARBY RELATED INCIDENTS
              </span>

              <small>
                READ ONLY
              </small>

            </div>


            {nearby.length >
            0
            ? nearby.map(item => (<div key={item.report.id} className="resource-row">

                      <div>

                        <strong>

                          {item.report
                    .incident_type}

                        </strong>


                        <small>

                          {item.report
                    .location}

                          {" · COMMAND NOTIFIED"}

                        </small>

                      </div>


                      <span>

                        {item.distance.toFixed(1)}

                        {" km"}

                      </span>

                    </div>))
            : (<div className="empty-module">

                  No other relevant
                  incidents nearby.

                </div>)}

          </div>

        </section>

      </main>

    </div>);
}
export default App;
