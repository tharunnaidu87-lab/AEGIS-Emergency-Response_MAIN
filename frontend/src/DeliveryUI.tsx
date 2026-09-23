import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { API_BASE } from './api';
import { enqueue, listOutbox, syncOutbox, rememberReceipt, type Queued } from './outbox';

export function OutboxStatus() {
  const [items, setItems] = useState<Queued[]>([]);
  const [online, setOnline] = useState(navigator.onLine);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    const refresh = () => { setOnline(navigator.onLine); void listOutbox().then(value => {
      if (active) { setItems(value); value.forEach(v => { if (v.receipt) rememberReceipt(v.receipt); }); }
    }).catch(() => { if (active) setError('Device storage is unavailable. Keep unsent information on screen.'); }); };
    const tick = () => { refresh(); void syncOutbox().catch(() => {}); };
    tick(); const timer = setInterval(tick, 10000);
    window.addEventListener('online', tick); window.addEventListener('offline', refresh);
    window.addEventListener('aegis-outbox', refresh);
    navigator.serviceWorker?.addEventListener('message', refresh);
    return () => { active = false; clearInterval(timer); window.removeEventListener('online', tick);
      window.removeEventListener('offline', refresh); window.removeEventListener('aegis-outbox', refresh);
      navigator.serviceWorker?.removeEventListener('message', refresh); };
  }, []);
  const pending = items.filter(i => i.state !== 'sent');
  return <aside className="delivery-status" aria-label="Report delivery">
    <strong>DEMONSTRATION — not connected to emergency services</strong>
    {(!online || pending.length > 0 || error) && <p role="status">{error || `${online ? 'Connection available' : 'OFFLINE'} · ${pending.length} saved report(s) awaiting delivery`}</p>}
    {pending.map(item => <a key={item.id} href={'/queued/' + item.id}>Open saved {item.path === '/distress' ? 'signal' : 'report'} · {item.created.slice(11, 16)}</a>)}
    {!!pending.length && <button onClick={() => void syncOutbox(true)}>Retry delivery</button>}
  </aside>;
}

export function QueuedReceipt() {
  const { localId } = useParams();
  const [item, setItem] = useState<Queued>();
  const [error, setError] = useState('');
  const [signalStatus, setSignalStatus] = useState('');
  const [reportId, setReportId] = useState('');
  useEffect(() => {
    let active = true;
    async function read() {
      try {
        const saved = (await listOutbox()).find(i => i.id === localId);
        if (!active) return;
        setItem(saved);
        if (!saved) { setError('This receipt is not stored in this browser.'); return; }
        if (saved.receipt) rememberReceipt(saved.receipt);
        if (saved.state === 'sent' && saved.path === '/distress') {
          const response = await fetch(API_BASE + '/distress/' + saved.id, { headers: { 'X-Report-Token': saved.receipt!.tracking_token }, signal: AbortSignal.timeout(10000) });
          if (response.ok) {
            const result = await response.json();
            if (!active) return;
            setSignalStatus(result.status.replaceAll('_', ' '));
            if (result.report_receipt) { rememberReceipt(result.report_receipt); setReportId(result.report_receipt.report.id); }
          }
        }
      } catch { if (active) setError('Connection interrupted. Your saved receipt remains on this device.'); }
    }
    void read(); const timer = setInterval(() => void read(), 3000);
    return () => { active = false; clearInterval(timer); };
  }, [localId]);
  return <main className="receipt-page"><Link to="/report">AEGIS · Reporter</Link>
    <h1>{item?.state === 'sent' ? 'REPORT DELIVERED' : item ? 'REPORT SAVED ON THIS DEVICE' : 'Opening receipt…'}</h1>
    <p role="status">{item?.state === 'sent' ? 'AEGIS Command has received this report. All response activity is simulated.' : 'Delivery is not confirmed. Keep this browser open; AEGIS will retry when connected.'}</p>
    <p>{signalStatus}</p><p>Local receipt: {localId}</p><p>{item?.message}</p><p role="status">{error}</p>
    {(item?.receipt?.report?.id || reportId) && <Link className="intake-primary" to={'/track/' + (item?.receipt?.report?.id || reportId)}>TRACK MY REPORT</Link>}
    {item?.state !== 'sent' && <button onClick={() => void syncOutbox(true)}>Retry delivery</button>}
    {item?.state === 'review' && <details><summary>Saved details for correction</summary><pre>{JSON.stringify({ ...item.payload, photos: undefined, audio: undefined }, null, 2)}</pre><Link to="/report">Create a corrected report</Link></details>}
  </main>;
}

export function SosButton() {
  const [seconds, setSeconds] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [gps, setGps] = useState<{ latitude: number; longitude: number; accuracy: number }>();
  useEffect(() => {
    if (seconds === null) return;
    if (seconds > 0) { const timer = setTimeout(() => setSeconds(n => n === null ? null : n - 1), 1000); return () => clearTimeout(timer); }
    setSeconds(null); setSaving(true);
    void enqueue('/distress', { kind: 'SOS', captured_at: new Date().toISOString(), online: navigator.onLine, ...gps })
      .then(id => { window.location.assign('/queued/' + id); })
      .catch(() => { setSaving(false); setError('SOS could not be saved. Keep this page open and retry.'); });
  }, [seconds, gps]);
  function activate() {
    setError(''); setSeconds(3);
    navigator.geolocation?.getCurrentPosition(p => setGps({ latitude: p.coords.latitude, longitude: p.coords.longitude, accuracy: p.coords.accuracy }), () => {}, { timeout: 2500, maximumAge: 30000 });
  }
  return <section className="sos-section" aria-label="Emergency SOS">
    <div><h2>Need immediate help?</h2><p>No description is required. SOS sends a high-priority signal to this AEGIS demonstration.</p><p>Location is optional. A known location enables assignment of the nearest available simulated police unit.</p></div>
    <div className="sos-control"><button className="sos-button" disabled={seconds !== null || saving} onClick={activate} aria-label="Activate SOS">SOS</button>
      {seconds !== null && <><p role="status" aria-live="assertive">SOS ACTIVATING · {seconds}</p><button className="sos-cancel" onClick={() => setSeconds(null)}>CANCEL SOS</button></>}
      {saving && <p role="status">Saving signal…</p>}{error && <p role="alert">{error}</p>}
    </div>
  </section>;
}
