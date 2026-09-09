import { useSyncExternalStore } from "react";

const eventName = "aegis-road-scenario";
function subscribe(listener: () => void) {
  window.addEventListener(eventName, listener);
  window.addEventListener("storage", listener);
  return () => { window.removeEventListener(eventName, listener); window.removeEventListener("storage", listener); };
}
export function useRoadScenario(fusionId?: string) {
  const key = "aegis.road-scenario." + (fusionId || "standby");
  const blocked = useSyncExternalStore(subscribe, () => {
    try { return localStorage.getItem(key) === "blocked"; } catch { return false; }
  }, () => false);
  function setBlocked(value: boolean) {
    try {
      if (value) localStorage.setItem(key, "blocked"); else localStorage.removeItem(key);
      window.dispatchEvent(new Event(eventName));
    } catch { /* Storage-disabled browsers retain baseline routing. */ }
  }
  return [blocked, setBlocked] as const;
}
