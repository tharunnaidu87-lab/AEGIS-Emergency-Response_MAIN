const API_BASE = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");
const TOKEN_KEY = "aegis_command_token";

export function getCommandToken() {
  return sessionStorage.getItem(TOKEN_KEY) || "";
}

export function setCommandToken(token: string) {
  if (token) sessionStorage.setItem(TOKEN_KEY, token);
  else sessionStorage.removeItem(TOKEN_KEY);
}

export function clearCommandToken() {
  sessionStorage.removeItem(TOKEN_KEY);
}

const nativeFetch = window.fetch.bind(window);

function isAegisBackendRequest(input: RequestInfo | URL) {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
  if (API_BASE.startsWith("http://") || API_BASE.startsWith("https://")) {
    return raw.startsWith(API_BASE);
  }
  return raw.startsWith(API_BASE + "/") || raw === API_BASE;
}

window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const token = getCommandToken();
  if (!token || !isAegisBackendRequest(input)) {
    return nativeFetch(input, init);
  }

  const headers = new Headers(init?.headers || (input instanceof Request ? input.headers : undefined));
  if (!headers.has("Authorization")) headers.set("Authorization", `Bearer ${token}`);

  return nativeFetch(input, { ...init, headers });
};
