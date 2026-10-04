/** ZaminTahlil REST API mijozi (/api/v1). Xatolar {code, message_uz} shaklida ApiError boʻladi. */

const API = "/api/v1";

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function req(path, opts = {}) {
  let res;
  try {
    res = await fetch(`${API}${path}`, {
      ...opts,
      headers: opts.body ? { "Content-Type": "application/json" } : undefined,
    });
  } catch (_e) {
    throw new ApiError(0, "NETWORK", "Server bilan aloqa yoʻq");
  }
  if (!res.ok) {
    let body = {};
    try { body = await res.json(); } catch (_e) { /* JSON emas */ }
    throw new ApiError(res.status, body.code || `HTTP_${res.status}`, body.message_uz || `Xatolik (${res.status})`);
  }
  return res;
}

const json = async (path, opts) => (await req(path, opts)).json();

export const api = {
  getSettings: () => json("/settings"),
  putSettings: (data) => json("/settings", { method: "PUT", body: JSON.stringify(data) }),
  startRecon: (aoi) => json("/recon", { method: "POST", body: JSON.stringify({ aoi }) }),
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
  usage: (id) => json(`/usage/runs/${id}`),
  /** PNG ni blob sifatida olib, object URL qaytaradi (tozalashda revoke qilinadi). */
  async imageUrl(path) {
    const res = await fetch(path);
    if (!res.ok) throw new ApiError(res.status, "IMAGE", "Tasvirni yuklab boʻlmadi");
    return URL.createObjectURL(await res.blob());
  },
  compositePath: (id, date, r, g, b) =>
    `${API}/recon/${id}/composite.png?date=${date}&r=${encodeURIComponent(r)}&g=${encodeURIComponent(g)}&b=${encodeURIComponent(b)}`,
};
