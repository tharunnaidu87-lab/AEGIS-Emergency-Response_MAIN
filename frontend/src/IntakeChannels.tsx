import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { parseIntake, submitReport, type IntakeExtraction, type IntakeUnknownField, type SpeechMetadataInput } from './api';
import IntakeMethodSelector from './IntakeMethodSelector';
import { useRecordedVoice } from './useRecordedVoice';
import { useIntakeLocation } from './useIntakeLocation';

type Channel = 'SMS' | 'CALL';
const unknownFields: IntakeUnknownField[] = ['people_affected', 'injured', 'trapped', 'spreading', 'structural_damage'];
const groups = ['Children', 'Elderly', 'Disabled', 'Pregnant', 'Medical dependent'];
const label = (value: boolean | null) => value === null ? 'Unknown' : value ? 'Yes' : 'No';

export default function IntakeChannels({ source }: { source: Channel }) {
  return <ChannelPage key={source} source={source} />;
}

function ChannelPage({ source }: { source: Channel }) {
  const [text, setText] = useState('');
  const [parsed, setParsed] = useState<IntakeExtraction | null>(null);
  const [draft, setDraft] = useState<IntakeExtraction | null>(null);
  const [parseState, setParseState] = useState<'idle' | 'waiting' | 'parsing' | 'ready' | 'error'>('idle');
  const [retry, setRetry] = useState(0);
  const [callRequest, setCallRequest] = useState<({ text: string; latitude?: number; longitude?: number; gps_verified: boolean } & SpeechMetadataInput) | null>(null);
  const [slow, setSlow] = useState(false);
  const [editing, setEditing] = useState(false);
  const [phone, setPhone] = useState('');
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState('');
  const [receipt, setReceipt] = useState('');
  const transcript = useRef<HTMLTextAreaElement>(null);
  const parsedText = useRef('');
  const sendingLock = useRef(false);
  const mounted = useRef(true);
  const location = useIntakeLocation();
  const voice = useRecordedVoice(changeText);
  const { latitude, longitude, gpsVerified, valid } = location;

  function changeText(value: string) {
    setText(value.slice(0, 5000)); setParsed(null); setDraft(null);
    setCallRequest(null);
    setParseState(value.trim() ? 'waiting' : 'idle'); setSendError('');
  }
  function analyzeCall() {
    setCallRequest({ text, gps_verified: gpsVerified, ...voice.metadata,
      ...(valid ? { latitude: Number(latitude), longitude: Number(longitude) } : {}) });
  }
  function startVoice(retryRecording = false) {
    setCallRequest(null); setParsed(null); setDraft(null);
    setParseState(text.trim() ? 'waiting' : 'idle');
    void voice.start(retryRecording);
  }
  // CALL starts only on explicit Analyze. Moving/editing GPS must not rebill NLP.
  const smsLatitude = source === 'SMS' ? latitude : '';
  const smsLongitude = source === 'SMS' ? longitude : '';
  const smsGps = source === 'SMS' && gpsVerified;
  const smsValid = source === 'SMS' && valid;
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  useEffect(() => {
    if (!text.trim() || voice.listening || voice.processing || (source === 'CALL' && !callRequest)) return;
    const controller = new AbortController();
    let slowTimer: ReturnType<typeof setTimeout> | undefined;
    const timer = setTimeout(async () => {
      setParseState('parsing'); setSlow(false);
      slowTimer = setTimeout(() => setSlow(true), 8000);
      try {
        const result = await parseIntake(source === 'CALL' ? { source, ...callRequest! } :
          { source, text, gps_verified: smsGps,
            ...(smsValid ? { latitude: Number(smsLatitude), longitude: Number(smsLongitude) } : {}) }, controller.signal);
        if (controller.signal.aborted) return;
        const preserveEdits = parsedText.current === text;
        setParsed(result);
        setDraft(current => preserveEdits && current ? current : result);
        parsedText.current = text;
        setParseState('ready');
      } catch {
        if (!controller.signal.aborted) setParseState('error');
      } finally {
        clearTimeout(slowTimer);
        if (!controller.signal.aborted) setSlow(false);
      }
    }, 650);
    return () => { controller.abort(); clearTimeout(timer); clearTimeout(slowTimer); };
  }, [text, source, smsLatitude, smsLongitude, smsGps, smsValid, retry, voice.listening, voice.processing, callRequest]);

  function edit<K extends keyof IntakeExtraction>(key: K, value: IntakeExtraction[K]) {
    setDraft(current => current ? { ...current, [key]: value } : current);
    setSendError('');
  }
  const countInvalid = draft ? ['people_affected', 'injured', 'trapped'].some(key => {
    const value = draft[key as 'injured'];
    return value !== null && (!Number.isInteger(value) || value < 0 || value > 1000000);
  }) || (draft.people_affected !== null && Math.max(draft.injured || 0, draft.trapped || 0) > draft.people_affected) : false;
  const canSend = draft && parsed && parseState === 'ready' && !voice.listening && !voice.processing &&
    draft.incident_type && draft.location?.trim() && valid && !countInvalid && !sending;
  async function send() {
    if (!canSend || !draft || sendingLock.current) return;
    sendingLock.current = true; setSending(true); setSendError('');
    try {
      const response = await submitReport({
        source, raw_content: text, phone, incident_type: draft.incident_type!,
        location: draft.location!.trim(), description: text,
        latitude: Number(latitude), longitude: Number(longitude), gps_verified: gpsVerified,
        people_affected: draft.people_affected ?? Math.max(draft.injured ?? 0, draft.trapped ?? 0),
        injured: draft.injured ?? 0, trapped: draft.trapped ?? 0,
        spreading: draft.spreading ?? false, structural_damage: draft.structural_damage ?? false,
        vulnerable_groups: draft.vulnerable_groups, hazard_intensity: draft.hazard_intensity,
        intake_unknown_fields: unknownFields.filter(key => draft[key] === null),
        intake_result_id: parsed?.result_id,
      });
      if (mounted.current) setReceipt(response.report.id);
    } catch {
      if (mounted.current) setSendError('We could not confirm delivery. Your message is still here. Check your connection and try again; no receipt has been confirmed.');
    } finally {
      sendingLock.current = false;
      if (mounted.current) setSending(false);
    }
  }

  function countInput(key: 'people_affected' | 'injured' | 'trapped', title: string) {
    return <label>{title}<input aria-label={title} type="number" min="0" max="1000000" step="1"
      placeholder="Unknown" value={draft?.[key] ?? ''} onChange={e => edit(key, e.target.value === '' ? null : Number(e.target.value))} />
      <small>Leave blank if unknown.</small></label>;
  }
  function flagInput(key: 'spreading' | 'structural_damage', title: string) {
    return <label>{title}<select aria-label={title} value={draft?.[key] === null ? '' : String(draft?.[key])}
      onChange={e => edit(key, e.target.value === '' ? null : e.target.value === 'true')}>
      <option value="">Unknown</option><option value="true">Yes</option><option value="false">No</option>
    </select></label>;
  }
  const incidentInput = <label>Incident type<select aria-label="Incident type" value={draft?.incident_type || ''}
    onChange={e => edit('incident_type', (e.target.value || null) as IntakeExtraction['incident_type'])}>
    <option value="">Choose the emergency</option>{['Fire', 'Flood', 'Accident', 'Landslide'].map(kind => <option key={kind}>{kind}</option>)}
  </select></label>;
  const locationInput = <label>Where is the emergency?<input aria-label="Where is the emergency?" maxLength={200}
    value={draft?.location || ''} onChange={e => edit('location', e.target.value || null)} placeholder="Street, landmark or area" /></label>;

  return <div className="aegis-shell">
    <header className="intake-header"><Link to="/report"><strong>AEGIS</strong><small>PUBLIC EMERGENCY INTAKE</small></Link><Link to="/command">COMMAND</Link></header>
    <main className="channel-page">
      <IntakeMethodSelector active={source} />
      {receipt ? <section className="intake-receipt" role="status">
        <small>SOURCE: {source}</small><h1>Your emergency report is saved.</h1>
        <p>Report ID: <strong>{receipt}</strong></p><p>Command can now review this incident. No resources were dispatched by voice or text extraction.</p>
        <Link className="intake-primary" to={'/track/' + receipt}>TRACK MY REPORT</Link>
        <Link to={'/command?report=' + encodeURIComponent(receipt)}>OPEN THIS INCIDENT IN COMMAND</Link>
      </section> : <>
        <section className="channel-intro">
          <small>{source === 'CALL' ? 'VOICE / CALL' : 'TEXT / SMS'}</small>
          <h1>{source === 'CALL' ? 'Voice emergency report' : 'Text emergency report'}</h1>
          <p>{source === 'CALL' ? 'Speak naturally. Review what AEGIS understood before sending.' : 'Describe the emergency in your own words. AEGIS will prepare the details for you.'}</p>
          <p className="intake-truth">Web reporting prototype. {source === 'CALL' ? 'Telephone calls' : 'SMS gateway'}: not connected to a telecom provider.</p>
        </section>
        <div className="channel-grid">
          <section className="intake-compose">
            <h2><span>01</span> {source === 'CALL' ? 'Tell us what happened' : 'Write your message'}</h2>
            {source === 'CALL' && <div className="voice-controls">
              <small>AUTO-DETECT LANGUAGE</small>
              <p className={'voice-status' + (voice.listening ? ' listening' : '')} role="status">{voice.listening ? `LISTENING... ${voice.seconds}s / 25s` : voice.processing ? voice.phase === 'acquiring' ? 'OPENING MICROPHONE...' : 'PROCESSING AUDIO...' : 'READY TO RECORD OR REVIEW'}</p>
              <div className="voice-actions">
                <button className="intake-primary" disabled={voice.listening || voice.processing || sending || !voice.supported} onClick={() => startVoice()}>START SPEAKING</button>
                <button disabled={!voice.listening} onClick={voice.stop}>STOP</button>
                <button disabled={voice.listening || voice.processing || sending || !voice.supported} onClick={() => startVoice(true)}>RETRY</button>
                <button disabled={voice.listening || voice.processing || sending} onClick={() => transcript.current?.focus()}>EDIT TRANSCRIPT</button>
              </div>
              <small>Record up to 25 seconds. Browser noise suppression and echo cancellation are requested. Audio goes through AEGIS to multilingual transcription. Browser fallback uses your browser locale and may use its online service.</small>
              {voice.detectedLanguage && <p>Detected language: <strong>{voice.detectedLanguage}</strong></p>}
              {voice.browserLanguage && <p>Browser recognition locale: {voice.browserLanguage} (not automatic language detection)</p>}
              {voice.notice && <p className="intake-notice">{voice.notice}</p>}
              {!voice.supported && <p className="intake-notice">Speech recognition is unavailable in this browser. Type or paste your transcript below.</p>}
              {voice.error && <p className="intake-notice" role="alert">{voice.error}</p>}
            </div>}
            <label className="transcript-label" htmlFor="intake-text">{source === 'CALL' ? 'Live transcript / edit transcript' : 'Emergency message'}</label>
            <textarea id="intake-text" ref={transcript} rows={6} maxLength={5000} value={text} readOnly={voice.listening || voice.processing || sending}
              onChange={e => changeText(e.target.value)} placeholder={source === 'CALL'
                ? 'There is a fire near the college hostel. Twenty people are inside and two are injured.'
                : 'Flood near Anna Nagar bridge. Water is increasing quickly. Around thirty people are trapped.'} />
            <div className="intake-text-footer"><small>{text.length} / 5000 characters</small><small>Review names, numbers and location before confirming.</small></div>
            {source === 'CALL' && <button className="intake-primary" disabled={!text.trim() || voice.listening || voice.processing || sending || parseState === 'parsing'} onClick={analyzeCall}>ANALYZE EMERGENCY</button>}
            <div className="intake-parse-status" role="status">
              {voice.listening ? 'Listening. Nothing will be sent until you stop and confirm.' :
                parseState === 'parsing' ? slow ? 'AEGIS may be waking up. Keep this page open; your text is safe.' : 'AEGIS is understanding your message...' :
                parseState === 'waiting' ? source === 'CALL' ? 'Review your transcript, then press ANALYZE EMERGENCY.' : 'Preparing your message...' : parseState === 'ready' ? 'Details ready. Please review them before sending.' :
                parseState === 'error' ? 'AEGIS could not process the message. Your text is kept. Check your connection or retry while the backend wakes up.' :
                'Start with what happened and where. Unknown details can stay blank.'}
              {parseState === 'error' && <button onClick={() => setRetry(value => value + 1)}>RETRY ANALYSIS</button>}
            </div>
            <section className="intake-location">
              <h3>Emergency location</h3><p role="status">{location.status}</p>
              <button disabled={sending} onClick={location.request}>USE MY LOCATION</button>
              <div className="intake-coordinate-grid">
                <label>Latitude<input aria-label="Latitude" inputMode="decimal" value={latitude} placeholder="Enter latitude"
                  disabled={sending} onChange={e => location.edit('latitude', e.target.value)} /></label>
                <label>Longitude<input aria-label="Longitude" inputMode="decimal" value={longitude} placeholder="Enter longitude"
                  disabled={sending} onChange={e => location.edit('longitude', e.target.value)} /></label>
              </div>
              <small>{valid ? gpsVerified ? 'BROWSER GPS PROVIDED' : 'MANUAL COORDINATES' : 'No coordinates are assumed. GPS or valid coordinates are needed for the incident map.'}</small>
            </section>
            <details className="intake-contact"><summary>Contact number (optional)</summary><label>Phone<input type="tel" maxLength={40} value={phone} onChange={e => setPhone(e.target.value)} /></label></details>
          </section>
          <section className="intake-review" aria-label="AEGIS understood">
            <h2><span>02</span> AEGIS UNDERSTOOD</h2>
            {!draft ? <p className="intake-empty">Your interpreted report will appear here. Nothing is submitted automatically.</p> : <>
              <dl className="intake-summary">
                <div><dt>Incident</dt><dd>{draft.incident_type || 'Unknown - please choose'}</dd></div>
                <div><dt>Location</dt><dd>{draft.location || 'Unknown - please add'}</dd></div>
                <div><dt>People affected</dt><dd>{draft.people_affected ?? 'Unknown'}</dd></div>
                <div><dt>Injured / trapped</dt><dd>{draft.injured ?? 'Unknown'} / {draft.trapped ?? 'Unknown'}</dd></div>
                <div><dt>Vulnerable groups</dt><dd>{draft.vulnerable_groups.join(', ') || 'Not stated'}</dd></div>
                <div><dt>Spreading</dt><dd>{label(draft.spreading)}</dd></div>
                <div><dt>Structural damage</dt><dd>{label(draft.structural_damage)}</dd></div>
              </dl>
              <div className="intake-confidence"><strong>{parsed?.confidence == null ? 'Unrated' : Math.round(parsed.confidence * 100) + '%'}</strong><span>Extraction confidence<br /><small>{parsed?.confidence_basis || 'Heuristic local rule score; not a calibrated probability.'}</small></span></div>
              <p className="intake-truth">{parsed?.method} {parsed?.nlp_model && `| ${parsed.nlp_model}`}. Check names and numbers. Dispatch remains a Command decision.</p>
              <div className="intake-questions" aria-label="Clarification questions">
                {parsed?.questions.map(question => <p key={question}>{question}</p>)}
              </div>
              <details className="intake-defaults"><summary>Field confidence (uncalibrated)</summary>
                <dl className="intake-summary">{Object.entries(parsed?.field_confidence || {}).map(([field, score]) => <div key={field}><dt>{field.replaceAll('_', ' ')}</dt><dd>{score === null ? 'Unrated' : `${Math.round(score * 100)}% (uncalibrated)`}</dd></div>)}</dl>
              </details>
              {parsed?.warnings.map(warning => <p className="intake-notice" key={warning}>{warning}</p>)}
              <button className="intake-edit" aria-expanded={editing} disabled={sending} onClick={() => setEditing(!editing)}>{editing ? 'DONE EDITING' : 'EDIT DETAILS'}</button>
              {editing ? <fieldset disabled={sending} className="intake-fields"><legend>Correct the interpreted details</legend>
                {incidentInput}{locationInput}{countInput('people_affected', 'People affected')}{countInput('injured', 'Injured')}{countInput('trapped', 'Trapped')}
                {flagInput('spreading', 'Is the situation spreading?')}{flagInput('structural_damage', 'Structural damage?')}
                <label className="intake-wide">Estimated hazard intensity: {Math.round(draft.hazard_intensity * 100)}%
                  <input aria-label="Estimated hazard intensity" type="range" min="0" max="1" step="0.05" value={draft.hazard_intensity} onChange={e => edit('hazard_intensity', Number(e.target.value))} />
                  <small>{draft.hazard_basis}</small></label>
                <div className="intake-wide intake-vulnerable"><span>Vulnerable groups mentioned</span>{groups.map(group => <label key={group}><input type="checkbox" checked={draft.vulnerable_groups.includes(group)}
                  onChange={e => edit('vulnerable_groups', e.target.checked ? [...draft.vulnerable_groups, group] : draft.vulnerable_groups.filter(item => item !== group))} />{group}</label>)}</div>
              </fieldset> : <div className="intake-questions">
                {!draft.incident_type && incidentInput}{!draft.location && locationInput}
                {draft.people_affected === null && <p>Approximately how many people are affected? Use Edit Details, or leave this unknown.</p>}
                {draft.spreading === null && <p>Is the situation spreading? Use Edit Details if you know.</p>}
              </div>}
              {countInvalid && <p className="intake-notice" role="alert">Use whole, nonnegative counts. Injured and trapped people cannot each exceed the affected total.</p>}
              <details className="intake-defaults"><summary>How unknown details are handled</summary><p>Unknown counts are kept as unknown in the intake record. Existing analysis uses zero for unstated injured/trapped counts, and at least the known injured/trapped count if the total is unknown. Unknown flags use false as an analysis default. This does not mean the danger is absent.</p></details>
              <p>Review the details, then confirm. Dispatch remains a Command decision.</p>
              <button className="intake-primary intake-send" disabled={!canSend} onClick={() => void send()}>{sending ? 'SENDING YOUR REPORT...' : 'SEND EMERGENCY REPORT'}</button>
              {!valid && <p className="intake-notice">Add GPS or valid incident coordinates before sending.</p>}
            </>}
            {sendError && <p className="intake-notice" role="alert">{sendError}</p>}
          </section>
        </div>
      </>}
    </main>
  </div>;
}
