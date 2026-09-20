import { useEffect, useRef, useState } from 'react';

type SpeechResult = { isFinal: boolean; [index: number]: { transcript: string } };
type Recognition = {
  continuous: boolean; interimResults: boolean; lang: string;
  start: () => void; stop: () => void; abort: () => void;
  onresult: ((event: { results: ArrayLike<SpeechResult> }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
};
type SpeechWindow = Window & { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };

const errors: Record<string, string> = {
  'not-allowed': 'Microphone permission was denied. Allow it in your browser settings, or type your report below.',
  'service-not-allowed': 'This browser cannot access speech recognition. You can type or paste a transcript below.',
  'no-speech': 'No speech was heard. Try again closer to the microphone, or type your report.',
  'audio-capture': 'No working microphone was found. Check your microphone or type your report.',
  network: 'Speech recognition could not connect. Your transcript is kept; retry or type the rest.',
  aborted: 'Recording stopped. You can review the transcript or try again.',
};

function clean(value: string) {
  return value.replace(/\s+/g, ' ').trim();
}

function wordKey(value: string) {
  return value.toLocaleLowerCase().replace(/[.,!?;:'"()[\]{}]/g, '');
}

function collapseAdjacentDuplicates(value: string) {
  const words = clean(value).split(' ').filter(Boolean);
  return words.filter((word, index) => index === 0 || wordKey(word) !== wordKey(words[index - 1])).join(' ');
}

function mergeTranscript(base: string, addition: string) {
  const left = collapseAdjacentDuplicates(base);
  const right = collapseAdjacentDuplicates(addition);
  if (!left) return right;
  if (!right) return left;

  const leftWords = left.split(' ');
  const rightWords = right.split(' ');
  const maxOverlap = Math.min(leftWords.length, rightWords.length);
  let overlap = 0;

  for (let size = maxOverlap; size > 0; size--) {
    const leftTail = leftWords.slice(-size).map(wordKey).join('\u0000');
    const rightHead = rightWords.slice(0, size).map(wordKey).join('\u0000');
    if (leftTail === rightHead) {
      overlap = size;
      break;
    }
  }

  if (!overlap) {
    const leftKey = leftWords.map(wordKey).join('\u0000');
    const rightKey = rightWords.map(wordKey).join('\u0000');
    if (rightKey.startsWith(leftKey + '\u0000')) return right;
    if (leftKey.startsWith(rightKey + '\u0000')) return left;
  }

  return collapseAdjacentDuplicates([...leftWords, ...rightWords.slice(overlap)].join(' '));
}

export function useBrowserVoiceIntake(text: string, onText: (value: string) => void) {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState('');
  const recognition = useRef<Recognition | null>(null);
  const supported = Boolean((window as SpeechWindow).SpeechRecognition || (window as SpeechWindow).webkitSpeechRecognition);
  useEffect(() => () => {
    const current = recognition.current;
    recognition.current = null;
    if (current) { current.onresult = null; current.onerror = null; current.onend = null; current.abort(); }
  }, []);

  function start(retry = false) {
    if (recognition.current) return;
    const Constructor = (window as SpeechWindow).SpeechRecognition || (window as SpeechWindow).webkitSpeechRecognition;
    if (!Constructor) { setError('Speech recognition is not supported here. Type or paste your transcript below.'); return; }
    let current: Recognition | null = null;
    try {
      current = new Constructor();
      recognition.current = current;
      current.lang = navigator.language || 'en'; current.continuous = true; current.interimResults = true;
      const prefix = retry ? '' : text.trim();
      if (retry) onText('');
      let heard = false;
      let failed = false;
      current.onresult = event => {
        if (recognition.current !== current) return;

        let finalTranscript = '';
        let interimTranscript = '';
        for (const result of Array.from(event.results)) {
          const segment = clean(result[0]?.transcript || '');
          if (!segment) continue;
          heard = true;
          if (result.isFinal) finalTranscript = mergeTranscript(finalTranscript, segment);
          else interimTranscript = mergeTranscript(interimTranscript, segment);
        }

        const sessionTranscript = mergeTranscript(finalTranscript, interimTranscript);
        onText(mergeTranscript(prefix, sessionTranscript));
      };
      current.onerror = event => {
        if (recognition.current !== current) return;
        failed = true;
        setError(errors[event.error] || 'Recording was interrupted. Review your transcript and retry if needed.');
        setListening(false);
      };
      current.onend = () => {
        if (recognition.current !== current) return;
        recognition.current = null;
        setListening(false);
        if (!heard && !failed) setError(errors['no-speech']);
      };
      setError(''); setListening(true); current.start();
    } catch {
      if (current) { current.onresult = null; current.onerror = null; current.onend = null; }
      recognition.current = null; setListening(false);
      setError('The microphone could not start. Check permission or type your report below.');
    }
  }

  function stop() {
    try { recognition.current?.stop(); }
    catch { setListening(false); recognition.current = null; }
  }
  return { supported, listening, error, start, stop };
}
