import { useState } from 'react';
import { encodeBlob } from './outbox';

export default function PhotoPicker({ photos, onChange }: { photos: string[]; onChange: (photos: string[]) => void }) {
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function select(files: FileList | null) {
    if (!files) return;
    setBusy(true); setError('');
    try {
      if (photos.length + files.length > 2) throw new Error('Choose up to two photos.');
      const added = [];
      for (const file of files) {
        if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 10 * 1024 * 1024) throw new Error('Use JPEG, PNG or WebP photos up to 10 MB each.');
        const bitmap = await createImageBitmap(file);
        try {
          if (bitmap.width * bitmap.height > 16000000) throw new Error('Choose a photo smaller than 16 megapixels.');
          const scale = Math.min(1, 1200 / Math.max(bitmap.width, bitmap.height));
          const canvas = document.createElement('canvas'); canvas.width = Math.round(bitmap.width * scale); canvas.height = Math.round(bitmap.height * scale);
          canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
          const blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob(b => b ? resolve(b) : reject(new Error('Photo conversion failed.')), 'image/jpeg', .75));
          if (blob.size > 700000) throw new Error('Choose a smaller photo for this connection.');
          added.push(await encodeBlob(blob));
        } finally { bitmap.close(); }
      }
      onChange([...photos, ...added]);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'This photo could not be opened. Choose another.'); }
    finally { setBusy(false); }
  }
  return <section className="photo-picker"><h2>Add incident photos <small>optional</small></h2><p>Add up to two photos. Images are resized and location metadata is removed.</p>
    <label>Choose photos from gallery or files<input type="file" accept="image/jpeg,image/png,image/webp" multiple disabled={busy || photos.length >= 2} onChange={e => { void select(e.target.files); e.target.value = ''; }} /></label>
    <label>Take a photo<input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" disabled={busy || photos.length >= 2} onChange={e => { void select(e.target.files); e.target.value = ''; }} /></label>
    <div className="photo-previews">{photos.map((photo, index) => <figure key={index}><img src={'data:image/jpeg;base64,' + photo} alt={'Selected emergency photo ' + (index + 1)} /><button onClick={() => onChange(photos.filter((_, i) => i !== index))}>Remove photo {index + 1}</button></figure>)}</div>
    {busy && <p role="status">Preparing photo…</p>}{error && <p role="alert">{error}</p>}
  </section>;
}
