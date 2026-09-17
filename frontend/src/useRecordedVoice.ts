import { saveVoiceDraft, loadVoiceDraft } from './outbox';
import { useEffect, useRef, useState } from 'react';
import { transcribeVoice, type SpeechMetadataInput, type VoiceTranscription } from './api';
import { useBrowserVoiceIntake } from './useVoiceIntake';

const mimeType = 'audio/webm;codecs=opus';
const fallbackMessage = 'Use browser speech, type your message, or submit the retained recording for review.';

export function useRecordedVoice(onText: (value: string) => void) {
  const [phase, setPhase] = useState<'idle' | 'acquiring' | 'listening' | 'processing'>('idle');
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState('');
  const [fallback, setFallback] = useState(false);
  const [recordedAudio, setRecordedAudio] = useState<Blob | null>(null);
  useEffect(() => { void loadVoiceDraft().then(blob => { if (blob) setRecordedAudio(blob); }).catch(() => {}); }, []);
  const [result, setResult] = useState<VoiceTranscription | null>(null);
  const [browserTranscript, setBrowserTranscript] = useState('');
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const upload = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const busy = useRef(false);
  const stopRef = useRef<() => void>(() => {});
  const onTextRef = useRef(onText);
  useEffect(() => { onTextRef.current = onText; }, [onText]);
  const browser = useBrowserVoiceIntake('', value => {
    setBrowserTranscript(value); setResult(null); onTextRef.current(value);
  });
  const primarySupported = Boolean(typeof navigator.mediaDevices?.getUserMedia === 'function' &&
    typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(mimeType));
  const listening = phase === 'listening' || browser.listening;
  const processing = phase === 'processing' || phase === 'acquiring';

  useEffect(() => () => {
    generation.current++; busy.current = false;
    upload.current?.abort();
    const current = recorder.current;
    if (current) {
      current.onstop = null; current.ondataavailable = null; current.onerror = null;
      if (current.state !== 'inactive') current.stop();
    }
    stream.current?.getTracks().forEach(track => track.stop());
  }, []);

  useEffect(() => {
    if (!listening) return;
    const started = Date.now();
    const timer = setInterval(() => {
      const elapsed = Math.floor((Date.now() - started) / 1000);
      setSeconds(elapsed);
      if (elapsed >= 25) stopRef.current();
    }, 250);
    return () => clearInterval(timer);
  }, [listening]);

  function stop() {
    if (recorder.current?.state === 'recording') recorder.current.stop();
    if (browser.listening) browser.stop();
  }
  useEffect(() => { stopRef.current = stop; });

  async function start(retry = false) {
    if (busy.current || browser.listening) return;
    setError(''); setSeconds(0);
    if (!primarySupported || (fallback && !retry)) {
      setFallback(true);
      browser.start(true);
      return;
    }
    busy.current = true;
    const currentGeneration = ++generation.current;
    setPhase('acquiring'); setFallback(false);
    try {
      const audioStream = await navigator.mediaDevices.getUserMedia({ audio: {
        echoCancellation: true, noiseSuppression: true, autoGainControl: true,
      } });
      if (generation.current !== currentGeneration) {
        audioStream.getTracks().forEach(track => track.stop()); return;
      }
      stream.current = audioStream;
      const current = new MediaRecorder(audioStream, { mimeType, audioBitsPerSecond: 64000 });
      recorder.current = current;
      const chunks: Blob[] = [];
      current.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      current.onerror = () => {
        current.onstop = null;
        if (current.state !== 'inactive') current.stop();
        audioStream.getTracks().forEach(track => track.stop());
        recorder.current = null; busy.current = false; setPhase('idle');
        setError('Recording was interrupted. Retry or type your transcript.');
      };
      current.onstop = async () => {
        audioStream.getTracks().forEach(track => track.stop());
        recorder.current = null; stream.current = null;
        if (generation.current !== currentGeneration) return;
        setPhase('processing');
        const controller = new AbortController();
        upload.current = controller;
        try {
          const audio = new Blob(chunks, { type: mimeType });
          setRecordedAudio(audio);
          await saveVoiceDraft(audio);
          const transcription = await transcribeVoice(audio, controller.signal);
          if (generation.current !== currentGeneration) return;
          setResult(transcription); setBrowserTranscript('');
          onTextRef.current(transcription.transcript);
        } catch {
          if (generation.current !== currentGeneration) return;
          setFallback(true);
          setError(browser.supported
            ? 'You can submit the retained recording, repeat with browser recognition, or type your message.'
            : 'Submit the retained recording for review, or type your message below.');
        } finally {
          if (generation.current === currentGeneration) { busy.current = false; setPhase('idle'); }
        }
      };
      current.start(250); setPhase('listening');
    } catch {
      stream.current?.getTracks().forEach(track => track.stop()); stream.current = null;
      if (generation.current !== currentGeneration) return;
      busy.current = false; setPhase('idle');
      setError('Microphone permission was denied or recording could not start. Allow access and retry, or type your transcript.');
    }
  }

  const metadata: SpeechMetadataInput = result ? { speech_result_id: result.result_id }
    : browserTranscript ? { browser_transcript: browserTranscript, browser_language: navigator.language || 'en' } : {};
  return { supported: primarySupported || browser.supported, listening, processing, phase, seconds,
    error: error || browser.error, notice: fallback ? fallbackMessage : '',
    detectedLanguage: result?.language_code || null,
    browserLanguage: browserTranscript ? navigator.language : null,
    recordedAudio, metadata, start, stop };
}
