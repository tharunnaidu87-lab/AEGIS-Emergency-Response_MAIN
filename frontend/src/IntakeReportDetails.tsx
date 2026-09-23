import type { SharedReport } from './api';

const fields = ['incident_type', 'location', 'people_affected', 'injured', 'trapped', 'vulnerable_groups', 'spreading', 'structural_damage', 'hazard_intensity'];
function display(value: unknown) {
  if (value === null || value === undefined) return 'Unknown';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (Array.isArray(value)) return value.join(', ') || 'Not stated';
  return String(value);
}

export default function IntakeReportDetails({ report }: { report: SharedReport }) {
  if (report.source === 'APP') return null;
  return <details className="command-intake-record" key={report.id}>
    <summary><strong>REPORTING CHANNEL: {report.source}</strong><span>Original {report.source === 'CALL' ? 'voice transcript' : 'SMS text'} and reviewed interpretation</span></summary>
    <p>Report: {report.id} | Fusion group: {report.fusion_id}</p>
    <blockquote>{report.intake?.original_transcript || report.raw_content || 'Original text is unavailable for this legacy report.'}</blockquote>
    {report.intake ? <>
      <p>Detected language: {report.intake.detected_language || 'Unknown'} | Speech provider: {report.intake.speech_provider || 'Legacy / unknown'} {report.intake.speech_model || ''}</p>
      {report.intake.browser_language_hint && <p>Browser locale (client reported, not detected): {report.intake.browser_language_hint}</p>}
      <p>Interpretation provider: {report.intake.nlp_provider || 'LOCAL'} | {report.intake.nlp_model || 'Local rules'} | {report.intake.nlp_method || report.intake.extraction.method}</p>
      <p><strong>Extraction confidence: {report.intake.extraction.confidence == null ? 'Unrated' : Math.round(report.intake.extraction.confidence * 100) + '%'}</strong></p>
      <p>{report.intake.confidence_basis}. The reviewed observations appear below; operational panels use the fused incident estimate.</p>
      <dl>{fields.map(key => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{display(report.intake!.reviewed[key])}</dd></div>)}</dl>
      <details><summary>Original structured interpretation and uncertain fields</summary>
        <dl>{fields.map(key => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{display(report.intake!.extraction[key as keyof typeof report.intake.extraction])}</dd></div>)}</dl>
        <p>Originally missing: {report.intake.missing_fields?.join(', ') || report.intake.extraction.missing_fields.join(', ') || 'None'}</p>
        <dl>{Object.entries(report.intake.field_confidence || {}).map(([key, score]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{score == null ? 'Unrated' : `${Math.round(score * 100)}% (uncalibrated)`}</dd></div>)}</dl>
      </details>
      {Object.entries(report.intake.citizen_corrections || {}).map(([key, correction]) => <p key={key}>Reporter correction - {key.replaceAll('_', ' ')}: {display(correction.original)} → {display(correction.reviewed)}</p>)}
      <p>Corrected fields: {report.intake.corrected_fields.map(key => key.replaceAll('_', ' ')).join(', ') || 'None'}.</p>
      {report.intake.unknown_fields.length > 0 && <p>Unstated values remain unknown here. Existing engines use documented zero/false defaults and a known-victim minimum for an unknown total.</p>}
    </> : <p>This older report has no saved interpretation record. Its original text and existing incident analysis remain available.</p>}
  </details>;
}
