const API_BASE = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");
const tokenKey = () => location.pathname.startsWith("/responder") ? "aegis_responder_token" : "aegis_command_token";

export function getCommandToken() {
  return sessionStorage.getItem(tokenKey()) || "";
}

export function setCommandToken(token: string) {
  if (token) sessionStorage.setItem(tokenKey(), token);
  else sessionStorage.removeItem(tokenKey());
}

export function clearCommandToken() {
  sessionStorage.removeItem(tokenKey());
}

const nativeFetch = window.fetch.bind(window);

function isAegisBackendRequest(input: RequestInfo | URL) {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
  const base = new URL(API_BASE, location.origin);
  const target = new URL(raw, location.origin);
  return target.origin === base.origin && (target.pathname === base.pathname || target.pathname.startsWith(base.pathname.replace(/\/$/, '') + '/'));
}

window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  if (!isAegisBackendRequest(input)) return nativeFetch(input, init);
  const headers = new Headers(init?.headers || (input instanceof Request ? input.headers : undefined));
  const path = new URL(typeof input === 'string' ? input : input instanceof URL ? input : input.url, location.origin).pathname;
  const tracking = /\/(?:reports|distress)\/([^/]+)$/.exec(path);
  if (tracking) {
    const receipt = localStorage.getItem('aegis-receipt-' + tracking[1]);
    if (receipt && !headers.has('X-Report-Token')) headers.set('X-Report-Token', receipt);
  }
  const staffPath = ['/command', '/simulate', '/relocation', '/responder'].includes(location.pathname);
  const token = staffPath ? getCommandToken() : '';
  if (token && !headers.has('Authorization')) headers.set('Authorization', `Bearer ${token}`);
  return nativeFetch(input, { ...init, headers });
};
