import { useCallback, useEffect, useRef, useState } from 'react';

export function useIntakeLocation() {
  const [latitude, setLatitude] = useState('');
  const [longitude, setLongitude] = useState('');
  const [gpsVerified, setGpsVerified] = useState(false);
  const [status, setStatus] = useState('AEGIS asks for GPS to place your report on the map. You can enter coordinates if unavailable.');
  const generation = useRef(0);
  const request = useCallback(() => {
    const token = ++generation.current;
    if (!navigator.geolocation) { setStatus('GPS is unavailable. Enter the incident latitude and longitude below.'); return; }
    setStatus('Waiting for location permission or a GPS fix...');
    navigator.geolocation.getCurrentPosition(position => {
      if (generation.current !== token) return;
      const { latitude: lat, longitude: lon } = position.coords;
      if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) {
        setStatus('A valid GPS fix was not received. Retry or enter coordinates.'); return;
      }
      setLatitude(lat.toFixed(6)); setLongitude(lon.toFixed(6)); setGpsVerified(true);
      setStatus('Device GPS added. If the emergency is elsewhere, edit the coordinates.');
    }, error => {
      if (generation.current !== token) return;
      setStatus(error.code === 1 ? 'Location permission was denied. You can enter the incident coordinates below.' :
        'GPS could not locate you. Retry or enter the incident coordinates below.');
    }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 });
  }, []);
  useEffect(() => {
    const cancel = () => { generation.current++; };
    const timer = window.setTimeout(request, 0);
    return () => { clearTimeout(timer); cancel(); };
  }, [request]);
  function edit(field: 'latitude' | 'longitude', value: string) {
    generation.current++; setGpsVerified(false);
    (field === 'latitude' ? setLatitude : setLongitude)(value);
    setStatus('Manual coordinates. Check that these identify the emergency.');
  }
  const valid = latitude.trim() !== '' && longitude.trim() !== '' &&
    Number.isFinite(Number(latitude)) && Number.isFinite(Number(longitude)) &&
    Math.abs(Number(latitude)) <= 90 && Math.abs(Number(longitude)) <= 180;
  return { latitude, longitude, gpsVerified, status, valid, request, edit };
}
