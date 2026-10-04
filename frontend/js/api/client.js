/**
 * ZaminTahlil REST API mijozi (/api/v1).
 * Kirish: har bir soʻrovda `Authorization: Basic` (username:parol, UTF-8) — token yoʻq.
 * 401 boʻlsa bir marta /auth/login qayta chaqiriladi (masalan, baza fayli oʻchirilgan boʻlsa foydalanuvchi
 * qayta yaratiladi); baribir 401 boʻlsa — kirish oynasi koʻrsatiladi.
 * Xatolar {code, message_uz} shaklida ApiError boʻladi.
 */

const API = "/api/v1";
const CREDS_KEY = "zt:auth";
let creds = null; // {username, password}
let onAuthRequired = null;

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function b64utf8(s) {
  const bytes = new TextEncoder().encode(s);
  let bin = "";
  bytes.forEach((b) => (bin += String.fromCharCode(b)));
  return btoa(bin);
}

export function setCredentials(c, persist = true) {
  creds = c;
  try {
    if (c && persist) sessionStorage.setItem(CREDS_KEY, JSON.stringify(c));
    else sessionStorage.removeItem(CREDS_KEY);
  } catch (_e) { /* brauzer xotirasi yoʻq — faqat shu sahifada */ }
}

export function loadStoredCredentials() {
  try {
    const raw = sessionStorage.getItem(CREDS_KEY);
    creds = raw ? JSON.parse(raw) : null;
  } catch (_e) {
    creds = null;
  }
  return creds;
}

export function currentUsername() {
  return creds?.username ?? null;
}

export function onAuthLost(fn) {
  onAuthRequired = fn;
}

function authHeaders() {
  return creds ? { Authorization: `Basic ${b64utf8(`${creds.username}:${creds.password}`)}` } : {};
}

async function raw(path, opts = {}) {
  try {
    return await fetch(`${API}${path}`, {
      ...opts,
      headers: { ...(opts.body ? { "Content-Type": "application/json" } : {}), ...authHeaders(), ...(opts.headers || {}) },
    });
  } catch (_e) {
    throw new ApiError(0, "NETWORK", "Server bilan aloqa yoʻq");
  }
}

async function toError(res) {
  let body = {};
  try { body = await res.json(); } catch (_e) { /* JSON emas */ }
  return new ApiError(res.status, body.code || `HTTP_${res.status}`, body.message_uz || `Xatolik (${res.status})`);
}

async function req(path, opts = {}, retry = true) {
  const res = await raw(path, opts);
  if (res.status === 401 && retry && creds && !path.startsWith("/auth/")) {
    // Foydalanuvchi bazadan yoʻqolgan boʻlishi mumkin (baza qayta yaratilgan) — qayta kirish
    const relog = await raw("/auth/login", { method: "POST", body: JSON.stringify(creds) });
    if (relog.ok) return req(path, opts, false);
    onAuthRequired?.();
  } else if (res.status === 401 && !path.startsWith("/auth/")) {
    onAuthRequired?.();
  }
  if (!res.ok) throw await toError(res);
  return res;
}

const json = async (path, opts) => (await req(path, opts)).json();

export const api = {
  login: async (username, password) => {
    const res = await raw("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
    if (!res.ok) throw await toError(res);
    return res.json();
  },
  getSettings: () => json("/settings"),
  putSettings: (data) => json("/settings", { method: "PUT", body: JSON.stringify(data) }),
  startRecon: (aoi, name) => json("/recon", { method: "POST", body: JSON.stringify({ aoi, name }) }),
  areas: () => json("/recon"),
  renameArea: (id, name) => json(`/recon/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  deleteArea: (id) => json(`/recon/${id}`, { method: "DELETE" }),
  active: () => json("/recon/active"),
  cancel: (id) => json(`/recon/${id}/cancel`, { method: "POST" }),
  run: (id) => json(`/recon/${id}`),
  layers: (id) => json(`/recon/${id}/layers`),
  pixel: (id, lon, lat) => json(`/recon/${id}/pixel?lon=${encodeURIComponent(lon)}&lat=${encodeURIComponent(lat)}`),
  classes: (id) => json(`/recon/${id}/classes`),
  changes: (id) => json(`/recon/${id}/changes`),
  weather: (id) => json(`/recon/${id}/weather`),
  satellites: (id) => json(`/recon/${id}/satellites`),
  report: (id) => json(`/recon/${id}/report`),
  generateReport: (id) => json(`/recon/${id}/report`, { method: "POST" }),
  terrain3d: (id, scope = "context") => json(`/recon/${id}/terrain3d?scope=${scope}`),
  labels: (id) => json(`/recon/${id}/labels`),
  chat: (id) => json(`/recon/${id}/chat`),
  ask: (id, message) => json(`/recon/${id}/chat`, { method: "POST", body: JSON.stringify({ message }) }),
  clearChat: (id) => json(`/recon/${id}/chat`, { method: "DELETE" }),
  usage: (id) => json(`/usage/runs/${id}`),
  /** PNG ni blob sifatida olib, object URL qaytaradi (tozalashda revoke qilinadi). */
  async imageUrl(path) {
    const res = await req(path.replace(API, ""));
    return URL.createObjectURL(await res.blob());
  },
  compositePath: (id, date, r, g, b) =>
    `${API}/recon/${id}/composite.png?date=${date}&r=${encodeURIComponent(r)}&g=${encodeURIComponent(g)}&b=${encodeURIComponent(b)}`,
  /** SSE oqimi fetch orqali (EventSource sarlavha yubora olmaydi). */
  stream: (path, signal) => req(path, { signal, headers: { Accept: "text/event-stream" } }),
};
