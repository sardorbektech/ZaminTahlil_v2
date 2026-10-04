/**
 * ZaminTahlil REST API mijozi.
 */

const API_BASE = "/api/v1";

export async function fetchSettings() {
  const res = await fetch(`${API_BASE}/settings`);
  return await res.json();
}

export async function updateSettings(data) {
  const res = await fetch(`${API_BASE}/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return await res.json();
}

export async function checkActiveRun() {
  const res = await fetch(`${API_BASE}/recon/active`);
  return await res.json();
}

export async function startRecon(aoiGeoJson) {
  const res = await fetch(`${API_BASE}/recon`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ aoi: aoiGeoJson }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.message_uz || "Rekognossirovkani boshlashda xatolik");
  }
  return await res.json();
}

export async function cancelRecon(runId) {
  const res = await fetch(`${API_BASE}/recon/${runId}/cancel`, {
    method: "POST",
  });
  return await res.json();
}

export async function fetchReconSummary(runId) {
  const res = await fetch(`${API_BASE}/recon/${runId}`);
  return await res.json();
}

export async function fetchReconLayers(runId) {
  const res = await fetch(`${API_BASE}/recon/${runId}/layers`);
  return await res.json();
}

export async function fetchPixelData(runId, lon, lat) {
  const res = await fetch(`${API_BASE}/recon/${runId}/pixel?lon=${lon}&lat=${lat}`);
  return await res.json();
}

export async function fetchClassDistribution(runId) {
  const res = await fetch(`${API_BASE}/recon/${runId}/classes`);
  return await res.json();
}

export async function fetchChangesSummary(runId) {
  const res = await fetch(`${API_BASE}/recon/${runId}/changes`);
  return await res.json();
}

export async function fetchWeatherData(runId) {
  const res = await fetch(`${API_BASE}/recon/${runId}/weather`);
  return await res.json();
}

export async function fetchSatellitesData(runId) {
  const res = await fetch(`${API_BASE}/recon/${runId}/satellites`);
  return await res.json();
}

export async function fetchAIReport(runId) {
  const res = await fetch(`${API_BASE}/recon/${runId}/report`);
  return await res.json();
}

export async function regenerateAIReport(runId) {
  const res = await fetch(`${API_BASE}/recon/${runId}/report`, {
    method: "POST",
  });
  return await res.json();
}

export async function fetchUsageSummary(runId) {
  const res = await fetch(`${API_BASE}/usage/runs/${runId}`);
  return await res.json();
}
