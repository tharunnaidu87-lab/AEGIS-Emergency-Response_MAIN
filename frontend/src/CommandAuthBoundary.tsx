import { useEffect, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { clearCommandToken, getCommandToken, setCommandToken } from "./commandAuthFetch";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");
const COMMAND_PATHS = new Set(["/command", "/simulate", "/relocation"]);

type LoginResponse = {
  status: string;
  role: "AUTHORITY";
  username: string;
  token: string;
  expires_at: number;
};

function currentPath() {
  return window.location.pathname;
}

function installHistoryEvents() {
  const historyAny = history as History & { __aegisPatched?: boolean };
  if (historyAny.__aegisPatched) return;
  historyAny.__aegisPatched = true;

  const originalPushState = history.pushState.bind(history);
  const originalReplaceState = history.replaceState.bind(history);

  history.pushState = (data: unknown, unused: string, url?: string | URL | null) => {
    originalPushState(data, unused, url);
    window.dispatchEvent(new Event("aegis-locationchange"));
  };

  history.replaceState = (data: unknown, unused: string, url?: string | URL | null) => {
    originalReplaceState(data, unused, url);
    window.dispatchEvent(new Event("aegis-locationchange"));
  };
}

export default function CommandAuthBoundary({ children }: { children: ReactNode }) {
  const [path, setPath] = useState(currentPath());
  const needsCommandAuth = useMemo(() => COMMAND_PATHS.has(path), [path]);
  const [checking, setChecking] = useState(needsCommandAuth && Boolean(getCommandToken()));
  const [authenticated, setAuthenticated] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    installHistoryEvents();
    const onLocation = () => setPath(currentPath());
    window.addEventListener("popstate", onLocation);
    window.addEventListener("aegis-locationchange", onLocation);
    return () => {
      window.removeEventListener("popstate", onLocation);
      window.removeEventListener("aegis-locationchange", onLocation);
    };
  }, []);

  useEffect(() => {
    if (!needsCommandAuth) {
      setAuthenticated(false);
      setChecking(false);
      return;
    }

    const token = getCommandToken();
    if (!token) {
      setAuthenticated(false);
      setChecking(false);
      return;
    }

    const controller = new AbortController();
    setChecking(true);
    fetch(`${API_BASE}/auth/command/session`, { signal: controller.signal })
      .then(response => {
        if (!response.ok) throw new Error("Session expired");
        return response.json();
      })
      .then(() => {
        if (!controller.signal.aborted) setAuthenticated(true);
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          clearCommandToken();
          setAuthenticated(false);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setChecking(false);
      });

    return () => controller.abort();
  }, [needsCommandAuth]);

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const response = await fetch(`${API_BASE}/auth/command/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
        signal: AbortSignal.timeout(60000),
      });
      if (!response.ok) {
        let detail = "Authority login failed.";
        try {
          const body = await response.json();
          if (typeof body.detail === "string") detail = body.detail;
        } catch {
          // Keep safe generic message.
        }
        throw new Error(detail);
      }
      const result: LoginResponse = await response.json();
      setCommandToken(result.token);
      setPassword("");
      setAuthenticated(true);
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : "Authority login failed.");
    } finally {
      setSubmitting(false);
    }
  }

  if (!needsCommandAuth) return <>{children}</>;

  if (checking) {
    return <main className="center-state"><h1>AEGIS COMMAND</h1><p>VERIFYING AUTHORITY SESSION...</p></main>;
  }

  if (!authenticated) {
    return (
      <main className="center-state" style={{ minHeight: "100vh" }}>
        <section style={{ width: "min(440px, 92vw)", border: "1px solid #31453d", padding: 28, background: "#0d1512" }}>
          <small>AEGIS // AUTHORITY ACCESS</small>
          <h1>Command Center Login</h1>
          <p>Authorized emergency command personnel only.</p>
          <form onSubmit={login} style={{ display: "grid", gap: 14 }}>
            <label>Username<input autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} required /></label>
            <label>Password<input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required /></label>
            {error && <p role="alert" style={{ color: "#ffb39d" }}>{error}</p>}
            <button className="intake-primary" disabled={submitting} type="submit">{submitting ? "VERIFYING..." : "ENTER COMMAND CENTER"}</button>
          </form>
          <p><a href="/report">RETURN TO PUBLIC REPORTING</a></p>
        </section>
      </main>
    );
  }

  return (
    <>
      <button
        type="button"
        onClick={() => { clearCommandToken(); setAuthenticated(false); }}
        style={{ position: "fixed", right: 18, bottom: 18, zIndex: 10000, padding: "9px 14px" }}
      >
        COMMAND LOGOUT
      </button>
      {children}
    </>
  );
}
