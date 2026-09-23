import { useEffect, useRef, useState } from 'react';

type SpeechResult = { isFinal: boolean; [index: number]: { transcript: string } };
type Recognition = {
  continuous: boolean; interimResults: boolean; lang: string;
  start: () => void; stop: () => void; abort: () => void;
  onresult: ((event: { resultIndex: number; results: ArrayLike<SpeechResult> }) => void) | null;
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

export function useBrowserVoiceIntake(text: string, onText: (value: string) => void, language?: string) {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState('');
  const recognition = useRef<Recognition | null>(null);
  const sessionActive = useRef(false);
  const sessionStartedAt = useRef(0);
  const accumulated = useRef('');
  const restartTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rotateTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const supported = Boolean((window as SpeechWindow).SpeechRecognition || (window as SpeechWindow).webkitSpeechRecognition);

  function clearRestartTimer() {
    if (restartTimer.current) {
      clearTimeout(restartTimer.current);
      restartTimer.current = null;
    }
  }

  function clearRotateTimer() {
    if (rotateTimer.current) {
      clearTimeout(rotateTimer.current);
      rotateTimer.current = null;
    }
  }

  useEffect(() => () => {
    sessionActive.current = false;
    clearRestartTimer();
    clearRotateTimer();
    const current = recognition.current;
    recognition.current = null;
    if (current) {
      current.onresult = null; current.onerror = null; current.onend = null;
      try { current.abort(); } catch {}
    }
  }, []);

  function launchRecognition() {
    if (!sessionActive.current || recognition.current) return;
    const Constructor = (window as SpeechWindow).SpeechRecognition || (window as SpeechWindow).webkitSpeechRecognition;
    if (!Constructor) {
      sessionActive.current = false;
      setListening(false);
      setError('Speech recognition is not supported here. Type or paste your transcript below.');
      return;
    }

    let current: Recognition | null = null;
    try {
      current = new Constructor();
      recognition.current = current;
      current.lang = language || navigator.language || 'en';
      current.continuous = true;
      current.interimResults = true;

      const baseTranscript = accumulated.current;
      const resultSlots: string[] = [];
      let latestSessionTranscript = '';
      let heardThisRun = false;
      let fatalError = false;

      current.onresult = event => {
        if (recognition.current !== current) return;

        for (let index = event.resultIndex; index < event.results.length; index++) {
          const segment = clean(event.results[index]?.[0]?.transcript || '');
          resultSlots[index] = segment;
          heardThisRun = heardThisRun || Boolean(segment);
        }

        latestSessionTranscript = resultSlots
          .map(collapseAdjacentDuplicates)
          .filter(Boolean)
          .reduce((value, segment) => mergeTranscript(value, segment), '');

        onText(mergeTranscript(baseTranscript, latestSessionTranscript));
      };

      current.onerror = event => {
        if (recognition.current !== current) return;

        if (event.error === 'no-speech') {
          // Mobile Chrome often ends a recognition run after a short pause.
          // Keep the overall AEGIS listening session alive and restart below.
          return;
        }

        if (event.error === 'aborted' && !sessionActive.current) return;

        fatalError = true;
        sessionActive.current = false;
        clearRestartTimer();
        setError(errors[event.error] || 'Recording was interrupted. Review your transcript and retry if needed.');
        setListening(false);
      };

      current.onend = () => {
        if (recognition.current !== current) return;
        clearRotateTimer();
        recognition.current = null;

        if (latestSessionTranscript) {
          accumulated.current = mergeTranscript(baseTranscript, latestSessionTranscript);
        }

        const elapsed = Date.now() - sessionStartedAt.current;
        if (sessionActive.current && !fatalError && elapsed < 25000) {
          // Some mobile browsers stop Web Speech after a pause even with
          // continuous=true. Restart transparently so the user can keep talking.
          restartTimer.current = setTimeout(() => {
            restartTimer.current = null;
            launchRecognition();
          }, 120);
          return;
        }

        sessionActive.current = false;
        setListening(false);
        if (!accumulated.current && !heardThisRun && !fatalError) {
          setError(errors['no-speech']);
        }
      };

      setError('');
      current.start();

      // Mobile Chrome commonly ends a Web Speech run around 15-16 seconds.
      // Rotate each recognition instance before that cap while preserving the
      // accumulated transcript, so the overall AEGIS session can continue.
      const remaining = 25000 - (Date.now() - sessionStartedAt.current);
      if (remaining > 3000) {
        rotateTimer.current = setTimeout(() => {
          rotateTimer.current = null;
          const activeRecognition = current;
          if (!activeRecognition || recognition.current !== activeRecognition || !sessionActive.current) return;
          try { activeRecognition.stop(); } catch {}
        }, Math.min(10000, Math.max(2500, remaining - 1200)));
      }
    } catch {
      if (current) {
        current.onresult = null; current.onerror = null; current.onend = null;
      }
      recognition.current = null;
      sessionActive.current = false;
      clearRestartTimer();
      setListening(false);
      setError('The microphone could not start. Check permission or type your report below.');
    }
  }

  function start(retry = false) {
    if (sessionActive.current || recognition.current) return;
    clearRestartTimer();
    clearRotateTimer();
    accumulated.current = retry ? '' : text.trim();
    if (retry) onText('');
    sessionStartedAt.current = Date.now();
    sessionActive.current = true;
    setError('');
    setListening(true);
    launchRecognition();
  }

  function stop() {
    sessionActive.current = false;
    clearRestartTimer();
    clearRotateTimer();
    setListening(false);
    const current = recognition.current;
    if (!current) return;
    try { current.stop(); }
    catch {
      recognition.current = null;
    }
  }

  return { supported, listening, error, start, stop };
}
