import { useEffect, useState } from 'react';
import { API_BASE, getReport } from './api';

export default function ReportPhotos({ reportId }: { reportId: string }) {
  const [photos, setPhotos] = useState<string[]>([]);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const urls: string[] = [];
    void (async () => {
      const report = await getReport(reportId);
      for (const id of report.photo_ids || []) {
        const response = await fetch(API_BASE + '/media/' + id, { signal: controller.signal,
          headers: { 'X-Report-Token': localStorage.getItem('aegis-receipt-' + reportId) || '' } });
        if (!response.ok) continue;
        const blob = await response.blob();
        if (!active) return;
        urls.push(URL.createObjectURL(blob));
      }
      if (active) setPhotos([...urls]);
    })().catch(() => {});
    return () => { active = false; controller.abort(); urls.forEach(url => URL.revokeObjectURL(url)); };
  }, [reportId]);
  if (!photos.length) return null;
  return <details className="photo-picker"><summary>Citizen supporting photos · unverified evidence</summary><div className="photo-previews">{photos.map((url, i) => <figure key={url}><a href={url} target="_blank" rel="noreferrer"><img src={url} alt={'Citizen supplied incident photo ' + (i + 1)} /></a></figure>)}</div></details>;
}
