import { useCallback, useEffect, useRef, useState } from "react";

// One in-flight read per mounted view. Stop scheduling after unmount; retain the
// last successful snapshot on network errors and preserve object identity if unchanged.
export function usePolling<T>(read: () => Promise<T>, initial: T, interval = 2500) {
  const [data, setData] = useState(initial);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const mounted = useRef(false);
  const pending = useRef<Promise<void> | null>(null);
  const signature = useRef("");
  const refresh = useCallback(async () => {
    if (pending.current) return pending.current;
    const task = (async () => {
      try {
        const next = await read();
        if (!mounted.current) return;
        const serialized = JSON.stringify(next);
        if (signature.current !== serialized) {
          signature.current = serialized;
          setData(next);
        }
        setError("");
      } catch (reason) {
        if (mounted.current) setError(reason instanceof Error ? reason.message : "AEGIS is unavailable.");
      } finally {
        if (mounted.current) setLoading(false);
      }
    })();
    pending.current = task;
    await task;
    pending.current = null;
  }, [read]);
  useEffect(() => {
    mounted.current = true;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      await refresh();
      if (!stopped) timer = setTimeout(poll, interval);
    }
    void poll();
    return () => { stopped = true; mounted.current = false; clearTimeout(timer); };
  }, [refresh, interval]);
  return { data, error, loading, refresh };
}
