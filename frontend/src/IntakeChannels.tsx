import { useEffect, useMemo, useRef, useState, } from "react";
import { listReports, submitReport, type EmergencyType, type SharedReport, } from "./api";
// ============================================================
// TYPES
// ============================================================
type ChannelSource = "SMS" | "CALL";
type Coordinates = {
    latitude: number;
    longitude: number;
};
type StructuredEmergency = {
    incidentType: EmergencyType;
    location: string;
    peopleAffected: number;
    hazardIntensity: number;
    vulnerableGroups: string[];
    spreading: boolean;
    structuralDamage: boolean;
    description: string;
    coordinates: Coordinates | null;
    extractionNotes: string[];
};
type EvidenceAssessment = {
    score: number;
    level: "LOW" | "MODERATE" | "HIGH" | "VERY HIGH";
    reasons: string[];
};
type FusionCandidate = {
    report: SharedReport;
    distanceKm: number | null;
    ageMinutes: number;
    score: number;
};
// ============================================================
// SPEECH RECOGNITION TYPES
// ============================================================
type SpeechAlternativeLike = {
    transcript: string;
};
type SpeechResultLike = {
    [index: number]: SpeechAlternativeLike;
    length: number;
    isFinal: boolean;
};
type SpeechEventLike = {
    results: ArrayLike<SpeechResultLike>;
};
type SpeechRecognitionLike = {
    continuous: boolean;
    interimResults: boolean;
    lang: string;
    start: () => void;
    stop: () => void;
    onresult: ((event: SpeechEventLike) => void) | null;
    onerror: (() => void) | null;
    onend: (() => void) | null;
};
type SpeechWindow = {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
};
// ============================================================
// BASIC HELPERS
// ============================================================
function radians(value: number) {
    return (value *
        Math.PI /
        180);
}
function distanceKm(firstLat: number, firstLon: number, secondLat: number, secondLon: number) {
    const radius = 6371;
    const dLat = radians(secondLat -
        firstLat);
    const dLon = radians(secondLon -
        firstLon);
    const a = Math.sin(dLat /
        2) ** 2
        +
            Math.cos(radians(firstLat))
                *
                    Math.cos(radians(secondLat))
                *
                    Math.sin(dLon /
                        2) ** 2;
    return (radius *
        2 *
        Math.atan2(Math.sqrt(a), Math.sqrt(1 -
            a)));
}
function normalizeText(value: string) {
    return value
        .replace(/\s+/g, " ")
        .trim();
}
function validCoordinates(latitude: number, longitude: number) {
    return (Number.isFinite(latitude)
        &&
            Number.isFinite(longitude)
        &&
            latitude >=
                -90
        &&
            latitude <=
                90
        &&
            longitude >=
                -180
        &&
            longitude <=
                180);
}
// ============================================================
// COORDINATE EXTRACTION
// ============================================================
function extractCoordinates(text: string): Coordinates | null {
    const match = text.match(/(-?\d{1,2}(?:\.\d+))\s*[, ]\s*(-?\d{1,3}(?:\.\d+))/);
    if (!match) {
        return null;
    }
    const latitude = Number(match[1]);
    const longitude = Number(match[2]);
    if (!validCoordinates(latitude, longitude)) {
        return null;
    }
    return {
        latitude,
        longitude,
    };
}
// ============================================================
// FEATURE 3
// INCIDENT TYPE EXTRACTION
// ============================================================
function detectIncidentType(text: string): EmergencyType {
    const value = text.toLowerCase();
    const fireWords = [
        "fire",
        "flames",
        "flame",
        "burning",
        "smoke",
        "explosion",
        "blaze",
    ];
    const floodWords = [
        "flood",
        "flooded",
        "water entering",
        "overflow",
        "overflowing",
        "submerged",
        "rising water",
        "heavy rain",
    ];
    const landslideWords = [
        "landslide",
        "mudslide",
        "rockfall",
        "slope failure",
        "rocks falling",
        "hill collapsed",
    ];
    const accidentWords = [
        "accident",
        "crash",
        "collision",
        "vehicle hit",
        "road accident",
        "bike crash",
        "car crash",
        "truck crash",
    ];
    if (fireWords.some(word => value.includes(word))) {
        return "Fire";
    }
    if (floodWords.some(word => value.includes(word))) {
        return "Flood";
    }
    if (landslideWords.some(word => value.includes(word))) {
        return "Landslide";
    }
    if (accidentWords.some(word => value.includes(word))) {
        return "Accident";
    }
    /*
      Backend currently supports these
      four normalized emergency types.
  
      Unknown/general emergency text is
      temporarily normalized to Accident.
    */
    return "Accident";
}
// ============================================================
// PEOPLE EXTRACTION
// ============================================================
function detectPeople(text: string) {
    const patterns = [
        /(\d+)\s*(?:people|persons|person|victims)/i,
        /(\d+)\s*(?:people\s+)?trapped/i,
        /(\d+)\s*(?:people\s+)?injured/i,
        /(\d+)\s*(?:residents|workers|students|passengers)/i,
        /about\s+(\d+)/i,
        /around\s+(\d+)/i,
    ];
    for (const pattern of patterns) {
        const match = text.match(pattern);
        if (match) {
            const value = Number(match[1]);
            if (Number.isFinite(value)
                &&
                    value >
                        0) {
                return value;
            }
        }
    }
    return 1;
}
// ============================================================
// LOCATION EXTRACTION
// ============================================================
function detectLocation(text: string) {
    const patterns = [
        /\b(?:at|near)\s+([^,.]{3,70})/i,
        /\b(?:inside|outside)\s+([^,.]{3,70})/i,
        /\bon\s+([^,.]{3,70})/i,
        /\bin\s+([^,.]{3,70})/i,
    ];
    for (const pattern of patterns) {
        const match = text.match(pattern);
        if (match
            &&
                match[1]) {
            let value = normalizeText(match[1]);
            const stopWords = [
                " and ",
                " with ",
                " where ",
                " there are ",
                " there is ",
                " people are ",
                " water is ",
                " fire is ",
            ];
            stopWords.forEach(stop => {
                const index = value
                    .toLowerCase()
                    .indexOf(stop);
                if (index >
                    2) {
                    value =
                        value.slice(0, index);
                }
            });
            if (value.length >=
                3) {
                return value;
            }
        }
    }
    return "";
}
// ============================================================
// VULNERABILITY EXTRACTION
// ============================================================
function detectVulnerableGroups(text: string) {
    const value = text.toLowerCase();
    const result: string[] = [];
    if ([
        "child",
        "children",
        "baby",
        "babies",
        "school students",
    ].some(word => value.includes(word))) {
        result.push("Children");
    }
    if ([
        "elderly",
        "senior citizen",
        "old people",
        "old man",
        "old woman",
    ].some(word => value.includes(word))) {
        result.push("Elderly");
    }
    if ([
        "disabled",
        "wheelchair",
        "mobility impaired",
    ].some(word => value.includes(word))) {
        result.push("Disabled");
    }
    if ([
        "oxygen",
        "ventilator",
        "patient",
        "medical dependent",
        "hospital patient",
    ].some(word => value.includes(word))) {
        result.push("Medical dependent");
    }
    return result;
}
// ============================================================
// SPREADING / STRUCTURAL DAMAGE
// ============================================================
function detectSpreading(text: string) {
    const value = text.toLowerCase();
    return [
        "spreading",
        "spread rapidly",
        "getting worse",
        "rising quickly",
        "water rising",
        "overflowing",
        "moving towards",
        "expanding",
        "fire spreading",
    ].some(word => value.includes(word));
}
function detectStructuralDamage(text: string) {
    const value = text.toLowerCase();
    return [
        "collapsed",
        "collapse",
        "building damaged",
        "bridge damaged",
        "cracked building",
        "wall fell",
        "roof fell",
        "structure damaged",
        "house damaged",
    ].some(word => value.includes(word));
}
// ============================================================
// HAZARD INTENSITY EXTRACTION
// ============================================================
function detectHazardIntensity(text: string) {
    const value = text.toLowerCase();
    const severe = [
        "massive",
        "severe",
        "critical",
        "very dangerous",
        "huge",
        "rapidly",
        "explosion",
        "raging",
        "completely flooded",
        "collapsed",
    ];
    if (severe.some(word => value.includes(word))) {
        return 0.9;
    }
    const moderate = [
        "heavy",
        "strong",
        "rising",
        "large",
        "serious",
        "many people",
    ];
    if (moderate.some(word => value.includes(word))) {
        return 0.75;
    }
    const low = [
        "small",
        "minor",
        "controlled",
        "slow",
        "limited",
    ];
    if (low.some(word => value.includes(word))) {
        return 0.4;
    }
    return 0.65;
}
// ============================================================
// COMPLETE STRUCTURED EXTRACTION
// ============================================================
function extractEmergency(rawText: string, manualLocation: string, manualLatitude: string, manualLongitude: string): StructuredEmergency {
    const normalized = normalizeText(rawText);
    const detectedCoordinates = extractCoordinates(normalized);
    const manualLat = Number(manualLatitude);
    const manualLon = Number(manualLongitude);
    const manualCoordinates = validCoordinates(manualLat, manualLon)
        ? {
            latitude: manualLat,
            longitude: manualLon,
        }
        : null;
    const coordinates = manualCoordinates
        ??
            detectedCoordinates;
    const incidentType = detectIncidentType(normalized);
    const extractedLocation = detectLocation(normalized);
    const location = normalizeText(manualLocation)
        ||
            extractedLocation;
    const peopleAffected = detectPeople(normalized);
    const vulnerableGroups = detectVulnerableGroups(normalized);
    const spreading = detectSpreading(normalized);
    const structuralDamage = detectStructuralDamage(normalized);
    const hazardIntensity = detectHazardIntensity(normalized);
    const extractionNotes: string[] = [];
    extractionNotes.push(`Incident normalized to ${incidentType}`);
    if (peopleAffected >
        1) {
        extractionNotes.push(`${peopleAffected} affected people extracted`);
    }
    else {
        extractionNotes.push("Affected population not clearly stated");
    }
    if (extractedLocation) {
        extractionNotes.push("Location phrase extracted from message");
    }
    if (detectedCoordinates) {
        extractionNotes.push("Coordinates detected inside raw message");
    }
    if (spreading) {
        extractionNotes.push("Hazard propagation indicator detected");
    }
    if (structuralDamage) {
        extractionNotes.push("Structural damage indicator detected");
    }
    return {
        incidentType,
        location,
        peopleAffected,
        hazardIntensity,
        vulnerableGroups,
        spreading,
        structuralDamage,
        description: normalized,
        coordinates,
        extractionNotes,
    };
}
// ============================================================
// FEATURE 6
// EVIDENCE QUALITY SCORE
// ============================================================
function calculateEvidenceQuality(text: string, phone: string, incident: StructuredEmergency, gpsVerified: boolean): EvidenceAssessment {
    const reasons: string[] = [];
    let score = 20;
    if (phone.trim().length >=
        8) {
        score +=
            10;
        reasons.push("Contact number supplied");
    }
    if (incident.location) {
        score +=
            15;
        reasons.push("Location information available");
    }
    if (incident.coordinates) {
        score +=
            gpsVerified
                ? 25
                : 18;
        reasons.push(gpsVerified
            ? "Device GPS verified"
            : "Coordinates available but not device-verified");
    }
    if (incident.peopleAffected >
        1) {
        score +=
            10;
        reasons.push("Affected population stated");
    }
    if (text.trim().length >=
        35) {
        score +=
            8;
        reasons.push("Detailed emergency description");
    }
    if (incident.spreading
        ||
            incident.structuralDamage) {
        score +=
            5;
        reasons.push("Operational hazard indicators supplied");
    }
    if (incident.vulnerableGroups.length >
        0) {
        score +=
            5;
        reasons.push("Vulnerable population information supplied");
    }
    score =
        Math.min(100, Math.round(score));
    let level: EvidenceAssessment["level"] = "LOW";
    if (score >=
        85) {
        level =
            "VERY HIGH";
    }
    else if (score >=
        70) {
        level =
            "HIGH";
    }
    else if (score >=
        50) {
        level =
            "MODERATE";
    }
    return {
        score,
        level,
        reasons,
    };
}
// ============================================================
// CROSS-CHANNEL FUSION MATCHING
// ============================================================
function locationSimilarity(first: string, second: string) {
    const a = first
        .toLowerCase()
        .replace(/[^a-z0-9 ]/g, "")
        .split(/\s+/)
        .filter(word => word.length >
        2);
    const b = new Set(second
        .toLowerCase()
        .replace(/[^a-z0-9 ]/g, "")
        .split(/\s+/)
        .filter(word => word.length >
        2));
    if (a.length ===
        0
        ||
            b.size ===
                0) {
        return 0;
    }
    const common = a.filter(word => b.has(word)).length;
    return (common /
        Math.max(a.length, b.size));
}
function findFusionCandidate(reports: SharedReport[], incident: StructuredEmergency): FusionCandidate | null {
    const now = Date.now();
    const candidates = reports
        .filter(report => report.status !==
        "RESOLVED")
        .filter(report => report.incident_type ===
        incident.incidentType)
        .map(report => {
        const ageMinutes = Math.abs(now -
            new Date(report.created_at).getTime())
            /
                60000;
        let distance: number | null = null;
        let score = 0;
        if (incident.coordinates) {
            distance =
                distanceKm(incident
                    .coordinates
                    .latitude, incident
                    .coordinates
                    .longitude, report.latitude, report.longitude);
            if (distance <=
                1) {
                score +=
                    60;
            }
            else if (distance <=
                3) {
                score +=
                    45;
            }
            else if (distance <=
                5) {
                score +=
                    20;
            }
        }
        const locationScore = locationSimilarity(incident.location, report.location);
        score +=
            locationScore *
                30;
        if (ageMinutes <=
            30) {
            score +=
                20;
        }
        else if (ageMinutes <=
            90) {
            score +=
                10;
        }
        return {
            report,
            distanceKm: distance,
            ageMinutes,
            score: Math.min(100, Math.round(score)),
        };
    })
        .filter(candidate => candidate.ageMinutes <=
        90)
        .filter(candidate => candidate.score >=
        40)
        .sort((first, second) => second.score -
        first.score);
    return candidates[0]
        ??
            null;
}
// ============================================================
// UI COMPONENT
// ============================================================
function IntakeChannels({ source }: { source: ChannelSource }) {
    return <ChannelPage key={source} source={source} />;
}
// ============================================================
// CHANNEL PAGE
// ============================================================
function ChannelPage({ source, }: {
    source: ChannelSource;
}) {
    const [rawText, setRawText] = useState("");
    const [phone, setPhone] = useState("");
    const [manualLocation, setManualLocation] = useState("");
    const [latitude, setLatitude] = useState("");
    const [longitude, setLongitude] = useState("");
    const [gpsVerified, setGpsVerified] = useState(false);
    const [reports, setReports] = useState<SharedReport[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [submittedId, setSubmittedId] = useState("");
    const [listening, setListening] = useState(false);
    const [speechSupported] = useState(() => Boolean((window as unknown as SpeechWindow).SpeechRecognition || (window as unknown as SpeechWindow).webkitSpeechRecognition));
    const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
    // ==========================================================
    // REPORT REFRESH FOR FUSION PREVIEW
    // ==========================================================
    useEffect(() => {
        let active = true;
        async function refresh() {
            try {
                const data = await listReports();
                if (active) {
                    setReports(data);
                }
            }
            catch (refreshError) {
                console.error(refreshError);
            }
        }
        void refresh();
        const timer = window.setInterval(() => {
            void refresh();
        }, 3000);
        return () => {
            active =
                false;
            window.clearInterval(timer);
        };
    }, []);
    // ==========================================================
    // SPEECH SUPPORT
    // ==========================================================
    useEffect(() => {
        return () => {
            recognitionRef.current
                ?.stop();
        };
    }, []);
    // ==========================================================
    // EXTRACTION
    // ==========================================================
    const structured = useMemo(() => extractEmergency(rawText, manualLocation, latitude, longitude), [
        rawText,
        manualLocation,
        latitude,
        longitude,
    ]);
    const evidence = useMemo(() => calculateEvidenceQuality(rawText, phone, structured, gpsVerified), [
        rawText,
        phone,
        structured,
        gpsVerified,
    ]);
    const fusionCandidate = useMemo(() => findFusionCandidate(reports, structured), [
        reports,
        structured,
    ]);
    // ==========================================================
    // GPS
    // ==========================================================
    function useDeviceGps() {
        setError("");
        if (!navigator.geolocation) {
            setError("Device GPS is unavailable.");
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
        }, () => {
            setError("Unable to obtain device GPS.");
        });
    }
    // ==========================================================
    // CALL SPEECH TO TEXT
    // ==========================================================
    function startSpeechRecognition() {
        if (source !==
            "CALL") {
            return;
        }
        const speechWindow = window as unknown as SpeechWindow;
        const Constructor = speechWindow
            .SpeechRecognition
            ??
                speechWindow
                    .webkitSpeechRecognition;
        if (!Constructor) {
            setError("Speech recognition is unavailable. Paste or type the call transcript instead.");
            return;
        }
        try {
            const recognition = new Constructor();
            recognition.continuous =
                true;
            recognition.interimResults =
                true;
            recognition.lang =
                "en-IN";
            recognition.onresult =
                event => {
                    let transcript = "";
                    for (let index = 0; index <
                        event.results.length; index++) {
                        const result = event.results[index];
                        const alternative = result[0];
                        if (alternative) {
                            transcript +=
                                alternative.transcript
                                    +
                                        " ";
                        }
                    }
                    setRawText(normalizeText(transcript));
                };
            recognition.onerror =
                () => {
                    setListening(false);
                    setError("Speech recognition stopped because of a microphone or browser error.");
                };
            recognition.onend =
                () => {
                    setListening(false);
                };
            recognitionRef.current =
                recognition;
            recognition.start();
            setListening(true);
            setError("");
        }
        catch (speechError) {
            console.error(speechError);
            setError("Unable to start browser speech recognition.");
        }
    }
    function stopSpeechRecognition() {
        recognitionRef.current
            ?.stop();
        setListening(false);
    }
    // ==========================================================
    // SUBMIT
    // ==========================================================
    async function submitChannelReport() {
        setError("");
        setSubmittedId("");
        if (!rawText.trim()) {
            setError(source ===
                "SMS"
                ? "Enter the emergency SMS."
                : "Enter or record the emergency call transcript.");
            return;
        }
        if (!structured.location) {
            setError("AEGIS could not determine the location. Enter the location manually.");
            return;
        }
        if (!structured.coordinates) {
            setError("Coordinates are required for routing. Use device GPS or enter latitude and longitude.");
            return;
        }
        setLoading(true);
        try {
            const response = await submitReport({
                source,
                raw_content: rawText,
                phone,
                incident_type: structured.incidentType,
                location: structured.location,
                latitude: structured
                    .coordinates
                    .latitude,
                longitude: structured
                    .coordinates
                    .longitude,
                people_affected: structured.peopleAffected,
                hazard_intensity: structured.hazardIntensity,
                description: structured.description,
                vulnerable_groups: structured.vulnerableGroups,
                gps_verified: gpsVerified,
                spreading: structured.spreading,
                structural_damage: structured.structuralDamage,
            });
            setSubmittedId(response.report.id);
            const updated = await listReports();
            setReports(updated);
        }
        catch (submitError) {
            console.error(submitError);
            setError("AEGIS could not send this channel report to the shared backend.");
        }
        finally {
            setLoading(false);
        }
    }
    // ==========================================================
    // UI
    // ==========================================================
    return (<div style={{
            minHeight: "100vh",
            background: "#080c0b",
            color: "#e5e9e6",
            fontFamily: "Inter, Arial, sans-serif",
        }}>

      {/* HEADER */}

      <header style={{
            minHeight: 64,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0 20px",
            borderBottom: "1px solid #303936",
            background: "#0b100f",
        }}>

        <div>

          <strong style={{
            fontSize: 16,
            letterSpacing: ".12em",
        }}>
            AEGIS
          </strong>


          <small style={{
            display: "block",
            marginTop: 3,
            color: "#75807c",
            fontSize: 8,
            letterSpacing: ".12em",
        }}>
            MULTI-CHANNEL EMERGENCY INTAKE
          </small>

        </div>


        <div style={{
            display: "flex",
            gap: 7,
        }}>

          <a href="/sms" style={{
            padding: "8px 11px",
            border: source ===
                "SMS"
                ? "1px solid #55cc94"
                : "1px solid #36403d",
            color: source ===
                "SMS"
                ? "#75e1aa"
                : "#8d9793",
            textDecoration: "none",
            fontSize: 8,
        }}>
            SMS
          </a>


          <a href="/call" style={{
            padding: "8px 11px",
            border: source ===
                "CALL"
                ? "1px solid #55cc94"
                : "1px solid #36403d",
            color: source ===
                "CALL"
                ? "#75e1aa"
                : "#8d9793",
            textDecoration: "none",
            fontSize: 8,
        }}>
            CALL
          </a>

        </div>

      </header>


      <main style={{
            width: "min(1280px, calc(100% - 30px))",
            margin: "0 auto",
            padding: "22px 0 40px",
        }}>

        {/* CHANNEL TITLE */}

        <section style={{
            marginBottom: 15,
            padding: 15,
            border: "1px solid #313b38",
            background: "#0d1211",
        }}>

          <small style={{
            color: "#5fd19a",
            fontSize: 8,
            letterSpacing: ".12em",
        }}>
            {source}
            {" / DEMONSTRATION GATEWAY"}
          </small>


          <h1 style={{
            margin: "8px 0",
            fontSize: 24,
        }}>

            {source ===
            "SMS"
            ? "Emergency SMS Intake"
            : "AI Call Intake Prototype"}

          </h1>


          <p style={{
            margin: 0,
            color: "#8f9995",
            fontSize: 11,
            lineHeight: 1.6,
        }}>

            {source ===
            "SMS"
            ? "Citizen sends only an SMS. This gateway represents AEGIS receiving and structuring that message."
            : "Citizen calls AEGIS. Browser speech-to-text is used for the prototype, then the transcript is structured into an emergency report."}

          </p>

        </section>


        <div style={{
            display: "grid",
            gridTemplateColumns: "minmax(320px,1fr) minmax(320px,1fr)",
            gap: 12,
        }}>

          {/* LEFT INPUT */}

          <section style={{
            padding: 15,
            border: "1px solid #313b38",
            background: "#0d1211",
        }}>

            <SectionTitle number="01" title={source ===
            "SMS"
            ? "RAW SMS"
            : "RAW CALL TRANSCRIPT"}/>


            {source ===
            "CALL" && (<div style={{
                display: "flex",
                gap: 7,
                marginBottom: 10,
            }}>

                <button type="button" disabled={listening
                ||
                    !speechSupported} onClick={startSpeechRecognition} style={actionButtonStyle}>

                  {speechSupported
                ? "START MICROPHONE"
                : "SPEECH API UNAVAILABLE"}

                </button>


                <button type="button" disabled={!listening} onClick={stopSpeechRecognition} style={actionButtonStyle}>
                  STOP
                </button>

              </div>)}


            {listening && (<div style={{
                marginBottom: 10,
                padding: 8,
                border: "1px solid #44705a",
                background: "rgba(52,150,100,.08)",
                color: "#70d7a1",
                fontSize: 8,
            }}>
                ● LISTENING / SPEECH-TO-TEXT ACTIVE
              </div>)}


            <textarea value={rawText} onChange={event => setRawText(event.target.value)} placeholder={source ===
            "SMS"
            ? "Example: Huge fire near Central Market. 15 people trapped, children inside. Fire is spreading rapidly."
            : "Example: There is severe flooding near River Road. Around 40 people are trapped and the water is rising quickly."} style={{
            width: "100%",
            minHeight: 155,
            boxSizing: "border-box",
            resize: "vertical",
            padding: 12,
            border: "1px solid #38423f",
            background: "#090d0c",
            color: "#e5e9e6",
            fontFamily: "inherit",
            lineHeight: 1.5,
        }}/>


            <SectionTitle number="02" title="SOURCE METADATA"/>


            <Input label="Phone / caller ID" value={phone} placeholder="Optional" onChange={setPhone}/>


            <Input label="Location override" value={manualLocation} placeholder="Use if NLP cannot determine location" onChange={setManualLocation}/>


            <div style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 8,
        }}>

              <Input label="Latitude" value={latitude} placeholder="13.130000" onChange={value => {
            setLatitude(value);
            setGpsVerified(false);
        }}/>


              <Input label="Longitude" value={longitude} placeholder="80.220000" onChange={value => {
            setLongitude(value);
            setGpsVerified(false);
        }}/>

            </div>


            <button type="button" style={{
            ...actionButtonStyle,
            width: "100%",
            marginTop: 4,
        }} onClick={useDeviceGps}>
              USE DEVICE GPS

              {gpsVerified
            ? " / VERIFIED"
            : ""}
            </button>


            {error && (<div style={{
                marginTop: 10,
                padding: 9,
                border: "1px solid #88413c",
                background: "rgba(140,45,37,.12)",
                color: "#f07970",
                fontSize: 9,
            }}>
                {error}
              </div>)}


            <button type="button" disabled={loading} onClick={() => {
            void submitChannelReport();
        }} style={{
            width: "100%",
            marginTop: 12,
            padding: 13,
            border: "1px solid #59cb95",
            background: "rgba(45,154,103,.12)",
            color: "#7ae0aa",
            fontWeight: 900,
            letterSpacing: ".08em",
            cursor: "pointer",
        }}>

              {loading
            ? "AEGIS PROCESSING..."
            : `SEND ${source} REPORT TO AEGIS`}

            </button>

          </section>


          {/* RIGHT INTELLIGENCE */}

          <section style={{
            display: "grid",
            gap: 12,
        }}>

            {/* NLP STRUCTURE */}

            <Panel>

              <SectionTitle number="03" title="STRUCTURED EXTRACTION"/>


              <Metric label="SOURCE NORMALIZED" value={source}/>


              <Metric label="INCIDENT TYPE" value={structured.incidentType}/>


              <Metric label="LOCATION" value={structured.location
            ||
                "NOT DETECTED"}/>


              <Metric label="PEOPLE" value={String(structured.peopleAffected)}/>


              <Metric label="HAZARD INTENSITY" value={`${Math.round(structured.hazardIntensity *
            100)}%`}/>


              <Metric label="SPREADING" value={structured.spreading
            ? "YES"
            : "NO"}/>


              <Metric label="STRUCTURAL DAMAGE" value={structured.structuralDamage
            ? "YES"
            : "NO"}/>


              <Metric label="VULNERABLE GROUPS" value={structured
            .vulnerableGroups
            .length >
            0
            ? structured
                .vulnerableGroups
                .join(" · ")
            : "NONE DETECTED"}/>


              <Metric label="COORDINATES" value={structured.coordinates
            ? `${structured.coordinates.latitude.toFixed(5)}, ${structured.coordinates.longitude.toFixed(5)}`
            : "NOT AVAILABLE"}/>


              <div style={{
            marginTop: 9,
            padding: 9,
            background: "#090d0c",
            border: "1px solid #303936",
        }}>

                {structured
            .extractionNotes
            .map(note => (<small key={note} style={{
                display: "block",
                padding: "3px 0",
                color: "#7f8985",
                fontSize: 8,
            }}>
                        ✓ {note}
                      </small>))}

              </div>

            </Panel>


            {/* EVIDENCE QUALITY */}

            <Panel>

              <SectionTitle number="04" title="EVIDENCE QUALITY"/>


              <div style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
        }}>

                <strong style={{
            fontSize: 28,
        }}>
                  {evidence.score}
                </strong>


                <span style={{
            color: evidence.score >=
                70
                ? "#66d99f"
                : evidence.score >=
                    50
                    ? "#dfad59"
                    : "#e56d64",
            fontSize: 10,
        }}>
                  {evidence.level}
                </span>

              </div>


              <div style={{
            height: 5,
            margin: "8px 0 10px",
            background: "#232a28",
        }}>

                <div style={{
            width: `${evidence.score}%`,
            height: "100%",
            background: evidence.score >=
                70
                ? "#58cc95"
                : evidence.score >=
                    50
                    ? "#d9a653"
                    : "#dc6259",
        }}/>

              </div>


              {evidence
            .reasons
            .map(reason => (<small key={reason} style={{
                display: "block",
                padding: "3px 0",
                color: "#7f8985",
                fontSize: 8,
            }}>
                      + {reason}
                    </small>))}

            </Panel>


            {/* FUSION */}

            <Panel>

              <SectionTitle number="05" title="CROSS-CHANNEL FUSION CHECK"/>


              {fusionCandidate
            ? (<div style={{
                    padding: 10,
                    border: "1px solid #4b795f",
                    background: "rgba(48,146,96,.09)",
                }}>

                    <small style={{
                    color: "#72d8a3",
                    fontWeight: 900,
                    letterSpacing: ".08em",
                }}>
                      LIKELY SAME INCIDENT
                    </small>


                    <strong style={{
                    display: "block",
                    margin: "7px 0 4px",
                }}>

                      {fusionCandidate
                    .report
                    .incident_type}

                      {" / "}

                      {fusionCandidate
                    .report
                    .location}

                    </strong>


                    <Metric label="EXISTING SOURCE" value={fusionCandidate
                    .report
                    .source}/>


                    <Metric label="MATCH SCORE" value={`${fusionCandidate.score}/100`}/>


                    <Metric label="AGE" value={`${Math.round(fusionCandidate.ageMinutes)} MIN`}/>


                    <Metric label="DISTANCE" value={fusionCandidate
                    .distanceKm !==
                    null
                    ? `${fusionCandidate.distanceKm.toFixed(2)} KM`
                    : "LOCATION-TEXT MATCH"}/>


                    <p style={{
                    margin: "8px 0 0",
                    color: "#8e9994",
                    fontSize: 8,
                    lineHeight: 1.5,
                }}>
                      Both reports remain
                      stored individually.
                      Command Intelligence
                      will logically fuse
                      corroborating reports
                      into one operational
                      incident.
                    </p>

                  </div>)
            : (<div style={{
                    padding: 10,
                    border: "1px solid #303936",
                    color: "#78837f",
                    fontSize: 9,
                }}>
                    NO RELATED ACTIVE REPORT
                    DETECTED.
                  </div>)}

            </Panel>


            {/* TRUTH */}

            <Panel>

              <SectionTitle number="06" title="IMPLEMENTATION TRUTH"/>


              <Metric label="BACKEND INGESTION" value="REAL"/>


              <Metric label="DATABASE STORAGE" value="REAL SQLITE"/>


              <Metric label="BROWSER SPEECH-TO-TEXT" value={source ===
            "CALL"
            ? speechSupported
                ? "AVAILABLE"
                : "UNAVAILABLE"
            : "N/A"}/>


              <Metric label="NLP EXTRACTION" value="RULE-BASED PROTOTYPE"/>


              <Metric label="EVIDENCE SCORE" value="RULE-BASED"/>


              <Metric label="INCIDENT FUSION" value="RULE-BASED COMMAND LAYER"/>


              <Metric label="REAL TELEPHONE NETWORK" value="NOT CONNECTED YET"/>


              <Metric label="REAL SMS PROVIDER" value="NOT CONNECTED YET"/>

            </Panel>

          </section>

        </div>


        {submittedId && (<section style={{
                marginTop: 12,
                padding: 15,
                border: "1px solid #4e8265",
                background: "rgba(50,145,96,.08)",
            }}>

            <small style={{
                color: "#70d7a1",
                fontWeight: 900,
            }}>
              AEGIS REPORT CREATED
            </small>


            <h2 style={{
                margin: "7px 0",
            }}>
              {submittedId}
            </h2>


            <span style={{
                color: "#8e9894",
                fontSize: 10,
            }}>
              This report is now visible
              to the Authority Command Center
              and the Command Intelligence
              fusion layer.
            </span>

          </section>)}

      </main>

    </div>);
}
// ============================================================
// SMALL UI COMPONENTS
// ============================================================
function Panel({ children, }: {
    children: React.ReactNode;
}) {
    return (<section style={{
            padding: 14,
            border: "1px solid #313b38",
            background: "#0d1211",
        }}>
      {children}
    </section>);
}
function SectionTitle({ number, title, }: {
    number: string;
    title: string;
}) {
    return (<div style={{
            display: "flex",
            gap: 8,
            alignItems: "center",
            margin: "4px 0 10px",
            paddingBottom: 6,
            borderBottom: "1px solid #29322f",
        }}>

      <small style={{
            color: "#596561",
            fontSize: 8,
        }}>
        {number}
      </small>


      <strong style={{
            fontSize: 10,
            letterSpacing: ".09em",
        }}>
        {title}
      </strong>

    </div>);
}
function Metric({ label, value, }: {
    label: string;
    value: string;
}) {
    return (<div style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 12,
            padding: "6px 0",
            borderBottom: "1px solid rgba(59,69,65,.35)",
        }}>

      <small style={{
            color: "#6f7a76",
            fontSize: 7,
        }}>
        {label}
      </small>


      <strong style={{
            maxWidth: "65%",
            textAlign: "right",
            fontSize: 8,
            lineHeight: 1.4,
        }}>
        {value}
      </strong>

    </div>);
}
function Input({ label, value, placeholder, onChange, }: {
    label: string;
    value: string;
    placeholder: string;
    onChange: (value: string) => void;
}) {
    return (<label style={{
            display: "block",
            marginBottom: 8,
            color: "#77827e",
            fontSize: 8,
        }}>

      {label}


      <input value={value} placeholder={placeholder} onChange={event => onChange(event.target.value)} style={{
            display: "block",
            width: "100%",
            boxSizing: "border-box",
            marginTop: 5,
            padding: 9,
            border: "1px solid #38423f",
            background: "#090d0c",
            color: "#e4e8e5",
            fontFamily: "inherit",
        }}/>

    </label>);
}
const actionButtonStyle: React.CSSProperties = {
    padding: "9px 11px",
    border: "1px solid #3c4944",
    background: "#111716",
    color: "#a8b1ad",
    fontSize: 8,
    fontWeight: 800,
    cursor: "pointer",
};
export default IntakeChannels;
