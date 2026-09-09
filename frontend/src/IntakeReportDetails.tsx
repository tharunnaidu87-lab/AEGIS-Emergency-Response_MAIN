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
    <summary><strong>SOURCE: {report.source}</strong><span>Original {report.source === 'CALL' ? 'voice transcript' : 'SMS text'} and reviewed interpretation</span></summary>
    <p>Report: {report.id} | Fusion: {report.fusion_id}</p>
    <blockquote>{report.raw_content || 'Original text is unavailable for this legacy report.'}</blockquote>
    {report.intake ? <>
      <p><strong>Extraction confidence: {Math.round(report.intake.extraction.confidence * 100)}%</strong> | LOCAL / RULE-BASED NLP</p>
      <p>{report.intake.confidence_basis}. Below are this citizen's reviewed observations; operational panels use the fused incident estimate.</p>
      <dl>{fields.map(key => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{display(report.intake!.reviewed[key])}</dd></div>)}</dl>
      <p>Corrected fields: {report.intake.corrected_fields.map(key => key.replaceAll('_', ' ')).join(', ') || 'None'}.</p>
      {report.intake.unknown_fields.length > 0 && <p>Unstated values remain unknown here. Existing engines use documented zero/false defaults and a known-victim minimum for an unknown total.</p>}
    </> : <p>This older report has no saved NLP extraction record. Its original text and existing incident analysis remain available.</p>}
  </details>;
}
