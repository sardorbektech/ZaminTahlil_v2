/** Sozlamalar oynasi: barcha sozlamalar (chegaralar backenddan), ulanishlar holati (kalitlarsiz). */
import { api } from "../api/client.js";
import { uz } from "../i18n/uz.js";
import { esc } from "./format.js";
import { toast } from "./toast.js";

const FIELDS = [
  "lookback_days", "weather_past_days", "weather_forecast_days", "max_scene_cloud_pct",
  "cloud_score_threshold", "s1_orbit_pass", "analysis_resolution_m", "max_aoi_km2",
  "gee_request_timeout_s", "gee_max_retries", "gee_max_concurrency", "ai_provider", "ai_model", "ai_history_size",
  "landcover_analyzer",
];
const STEP = { cloud_score_threshold: 0.01, max_aoi_km2: 0.01, max_scene_cloud_pct: 1, analysis_resolution_m: 1 };

let onSaved = null;

export function initSettings(cb) {
  onSaved = cb;
  const modal = document.getElementById("settings-modal");
  const close = () => (modal.hidden = true);
  document.getElementById("btn-settings-close").onclick = close;
  document.getElementById("btn-settings-cancel").onclick = close;
  document.getElementById("btn-settings-save").onclick = save;
}

export async function loadSettingsMeta() {
  return api.getSettings();
}

export async function openSettings() {
  const modal = document.getElementById("settings-modal");
  let data;
  try {
    data = await api.getSettings();
  } catch (e) {
    toast(e.message, "error");
    return;
  }
  const form = document.getElementById("settings-form");
  form.innerHTML = FIELDS.map((k) => {
    const v = data.settings[k];
    const label = esc(uz.settings.fields[k] || k);
    const choices = data.choices[k];
    if (choices) {
      return `<label>${label}<select name="${k}">${choices.map((c) => `<option value="${esc(c)}" ${c === v ? "selected" : ""}>${esc(uz.settings.choices[c] || c)}</option>`).join("")}</select></label>`;
    }
    if (typeof v === "number") {
      const [mn, mx] = data.limits[k] || [];
      return `<label>${label}<input type="number" name="${k}" value="${v}" ${mn !== undefined ? `min="${mn}" max="${mx}"` : ""} step="${STEP[k] ?? 1}"></label>`;
    }
    return `<label>${label}<input type="text" name="${k}" value="${esc(v)}"></label>`;
  }).join("");
  document.getElementById("settings-conn").innerHTML = `<span class="muted small">${esc(uz.settings.configured)}:</span>` +
    Object.entries(data.configured).map(([k, on]) => `<span class="badge ${on ? "on" : "off"}">${esc(uz.settings.conn[k] || k)}: ${on ? uz.common.yes : uz.common.no}</span>`).join("");
  modal.hidden = false;
}

async function save() {
  const form = document.getElementById("settings-form");
  const out = {};
  for (const el of form.elements) {
    if (!el.name) continue;
    out[el.name] = el.type === "number" ? Number(el.value) : el.value;
  }
  try {
    const res = await api.putSettings(out);
    toast(uz.settings.saved);
    document.getElementById("settings-modal").hidden = true;
    onSaved?.(res);
  } catch (e) {
    toast(e.message, "error");
  }
}
