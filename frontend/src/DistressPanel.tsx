import { useCallback, useState } from 'react';
import { API_BASE } from './api';
import { usePolling } from './usePolling';

type Signal = { id: string; kind: string; status: string; report_id?: string; has_audio: boolean;
  transcript?: string; priority: string; context: { latitude?: number; longitude?: number; accuracy?: number; text?: string; captured_at: string } };
function SignalCard({ signal, refresh }: { signal: Signal; refresh: () => Promise<void> }) {
  const [latitude, setLatitude] = useState(String(signal.context.latitude ?? '')); const [longitude, setLongitude] = useState(String(signal.context.longitude ?? ''));
  const [incidentType, setIncidentType] = useState('Fire'); const [people, setPeople] = useState(0);
  const [error, setError] = useState(''); const [audio, setAudio] = useState('');
  const [busy, setBusy] = useState(false);
  async function update(resource_type?: string) {
    setBusy(true); setError('');
    try {
      const payload = resource_type ? { resource_type } : { latitude: Number(latitude), longitude: Number(longitude), ...(signal.kind === 'VOICE' ? { incident_type: incidentType, people_affected: people } : {}) };
      if (!resource_type && (!latitude.trim() || !longitude.trim())) throw new Error('Enter both coordinates.');
      const response = await fetch(API_BASE + '/distress/' + signal.id, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(12000) });
      if (!response.ok) throw new Error('No compatible unit or valid location. Review and retry.');
      await refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Review this signal and retry.'); }
    finally { setBusy(false); }
  }
  async function play() {
    const response = await fetch(API_BASE + '/distress/' + signal.id + '/audio');
    if (response.ok) {
      // Small WebM recordings use data URLs, so there is no object URL lifecycle leak.
      const reader = new FileReader(); reader.onload = () => setAudio(String(reader.result)); reader.readAsDataURL(await response.blob());
    } else setError('Sign in again to open this recording.');
  }
  return <article className="signal-card"><h3>{signal.kind} · {signal.priority.replaceAll('_', ' ')}</h3><p>{signal.status.replaceAll('_', ' ')} · DEMO</p>
    <p>{signal.context.captured_at} · {signal.context.latitude == null ? 'Location needed; no nearest unit can be determined.' : `${signal.context.latitude}, ${signal.context.longitude} · accuracy ${signal.context.accuracy == null ? 'unknown' : Math.round(signal.context.accuracy) + ' m'} (device reported)`}</p>
    {signal.context.text && <blockquote>{signal.context.text}</blockquote>}{signal.transcript && <blockquote>{signal.transcript}</blockquote>}
    {signal.has_audio && <><button onClick={() => void play().catch(() => setError('Connection interrupted. Retry playback.'))}>Open retained recording</button>{audio && <audio controls src={audio} />}</>}
    {signal.kind === 'VOICE' && <p>Voice evidence awaits authority review. Use a reviewed incident report before approving a response.</p>}
    {!signal.report_id && <div className="signal-location">{signal.kind === 'VOICE' && <><label>Reviewed incident<select value={incidentType} onChange={e => setIncidentType(e.target.value)}>{['Fire','Flood','Landslide','Accident'].map(t => <option key={t}>{t}</option>)}</select></label><label>Known people affected<input type="number" min="0" value={people} onChange={e => setPeople(Number(e.target.value))} /></label></>}<label>Confirmed latitude<input type="number" min="-90" max="90" step="any" value={latitude} onChange={e => setLatitude(e.target.value)} /></label><label>Confirmed longitude<input type="number" min="-180" max="180" step="any" value={longitude} onChange={e => setLongitude(e.target.value)} /></label><button disabled={busy} onClick={() => void update()}>{signal.kind === 'SOS' ? 'Confirm location for demo SOS' : 'Create reviewed incident'}</button></div>}
    {signal.report_id && <><a href={'/command?report=' + signal.report_id}>Open incident and demo mission</a><details><summary>Authority override / escalation</summary><p>Add an available demo unit. Existing missions remain accountable; no real service is contacted.</p>{['POLICE', 'AMBULANCE', 'FIRE_ENGINE', 'RESCUE_TEAM'].map(type => <button key={type} disabled={busy} onClick={() => void update(type)}>{type.replaceAll('_', ' ')}</button>)}</details></>}
    {error && <p role="alert">{error}</p>}
  </article>;
}
export default function DistressPanel() {
  const read = useCallback(async () => { try { const response = await fetch(API_BASE + '/distress', { signal: AbortSignal.timeout(10000) }); if (!response.ok) throw new Error('Signal feed interrupted. Recheck your session and connection.'); return await response.json() as Signal[]; } catch { throw new Error('Signal feed interrupted. Recheck your session and connection.'); } }, []);
  const { data, error, refresh } = usePolling(read, [] as Signal[], 3000);
  if (!data.length && !error) return null;
  return <section className="distress-panel" aria-label="Priority distress signals"><h2>Priority signals · simulation</h2>{error && <p role="status">{error}</p>}{data.map(signal => <SignalCard key={signal.id} signal={signal} refresh={refresh} />)}</section>;
}
