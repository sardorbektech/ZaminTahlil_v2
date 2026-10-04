/**
 * ZaminTahlil frontend — faqat koʻrsatish va boshqaruv; barcha hisoblashlar backendda (/api/v1).
 * Holatlar: idle → ready → running → done | cancelled | error. Ishlayotganda faqat «Toʻxtatish» faol.
 */
import { api } from "./api/client.js";
import { listenRun } from "./api/sse.js";
import { applyI18n, uz } from "./i18n/uz.js";
import { areaKm2, clearAoi, drawShape, geometry, getAoiLayer, getMap, initMap, setMapLocked, showAoi } from "./map/leaflet_init.js";
import { initOverlays, setBounds } from "./map/overlays.js";
import { openPixelPopup } from "./map/pixel_popup.js";
import { startScan, stopScan } from "./map/scan_animation.js";
import { S, store } from "./state.js";
import { clearDates, initDateSlider, setDates } from "./ui/date_slider.js";
import { loadInfo, resetInfo, setInfoDate } from "./ui/info_panel.js";
import { initLayersPanel, loadLayers, resetLayers, setLayersDate, setLayersLocked } from "./ui/layers_panel.js";
import { repaginateAll } from "./ui/paginate.js";
import { downloadReport, renderReport, renderUsage, reportGenerating } from "./ui/report_view.js";
import { loadSatellites, resetSatellites } from "./ui/satellites_panel.js";
import { initSettings, openSettings } from "./ui/settings_modal.js";
import { initTabs } from "./ui/tabs.js";
import { toast } from "./ui/toast.js";
import { loadWeather, resetWeather } from "./ui/weather_panel.js";

const LAST_RUN_KEY = "zt:lastRun";
let sse = null;
let lockedEls = [];

const $ = (id) => document.getElementById(id);

function remember(id) {
  try { id ? localStorage.setItem(LAST_RUN_KEY, String(id)) : localStorage.removeItem(LAST_RUN_KEY); } catch (_e) { /* saqlab boʻlmadi */ }
}

function recall() {
  try { return parseInt(localStorage.getItem(LAST_RUN_KEY) || "", 10) || null; } catch (_e) { return null; }
}

// ---------------------------------------------------------------------------
// UI qulfi va holat
// ---------------------------------------------------------------------------
function setLocked(locked) {
  document.body.classList.toggle("locked", locked);
  setMapLocked(locked);
  setLayersLocked(locked);
  if (locked) {
    lockedEls = Array.from(document.querySelectorAll("#app button, #app input, #app select")).filter(
      (el) => el.id !== "btn-stop" && !el.disabled,
    );
    lockedEls.forEach((el) => (el.disabled = true));
  } else {
    lockedEls.forEach((el) => (el.disabled = false));
    lockedEls = [];
  }
}

function updateUI() {
  const running = store.state === S.RUNNING;
  if (running !== document.body.classList.contains("locked")) setLocked(running);
  $("state-badge").textContent = uz.states[store.state];
  $("btn-stop").disabled = !running;
  if (!running) {
    $("btn-recon").disabled = !store.aoi || store.areaKm2 > store.maxAoiKm2;
  }
  const map = getMap();
  if (running) startScan(map, getAoiLayer());
  else stopScan(map);
}

function setProgress(frac, text) {
  $("progress-fill").style.width = `${Math.round((frac || 0) * 100)}%`;
  $("progress-text").textContent = text || uz.bottom.progress_idle;
}

// ---------------------------------------------------------------------------
// Natijalar
// ---------------------------------------------------------------------------
function clearResults() {
  getMap()?.closePopup();
  resetLayers(); // overlaylar olib tashlanadi, object URL lar revoke qilinadi
  resetInfo();
  resetWeather();
  resetSatellites();
  renderReport(null, null);
  renderUsage(null);
  clearDates();
  store.patch({ runId: null });
}

async function loadResults(runId) {
  const run = await api.run(runId);
  if (run.status !== "completed") throw new Error(run.error?.message_uz || uz.states.error);
  store.patch({ runId });
  remember(runId);
  setBounds(L.latLngBounds(run.bounds_latlon));
  const date = setDates(run.observation_dates);
  const [layers, classes, changes, sats, weather, usage] = await Promise.all([
    api.layers(runId), api.classes(runId), api.changes(runId), api.satellites(runId), api.weather(runId), api.usage(runId),
  ]);
  setLayersDate(date);
  setInfoDate(date);
  loadLayers(runId, layers.layers);
  loadInfo({ run, summary: run, classes, changes, sats });
  loadWeather(weather);
  loadSatellites(sats);
  renderUsage(usage);
  let rep = null;
  try { rep = await api.report(runId); } catch (_e) { rep = null; }
  renderReport(rep, runId);
  return run;
}

// ---------------------------------------------------------------------------
// Run oqimi
// ---------------------------------------------------------------------------
function follow(runId) {
  sse?.close();
  sse = listenRun(runId, (ev) => onEvent(runId, ev), () => {
    if (store.state === S.RUNNING) toast(uz.toasts.connection_lost, "error");
  });
}

async function onEvent(runId, ev) {
  switch (ev.type) {
    case "progress":
      setProgress(ev.progress, `${ev.stage}/${ev.total_stages} · ${ev.message_uz}`);
      break;
    case "failover":
      toast(uz.toasts.failover, "warn");
      break;
    case "warning":
      toast(ev.message_uz, "warn", 6000);
      break;
    case "duplicate": {
      toast(uz.toasts.no_new_data, "info", 5000);
      const existing = ev.data.existing_run_id;
      setProgress(1, uz.toasts.no_new_data);
      store.set(S.DONE);
      try { await loadResults(existing); } catch (e) { toast(e.message, "error"); }
      break;
    }
    case "done":
      setProgress(1, ev.message_uz);
      store.set(S.DONE);
      toast(uz.toasts.done);
      try { await loadResults(runId); } catch (e) { toast(e.message, "error"); }
      break;
    case "error":
      setProgress(0, ev.message_uz);
      toast(ev.message_uz, "error", 7000);
      store.set(S.ERROR);
      clearResults();
      break;
    case "cancelled":
      onCancelled();
      break;
    default:
      break;
  }
}

function onCancelled() {
  sse?.close();
  if (store.state !== S.RUNNING) return;
  clearResults();
  setProgress(0, uz.toasts.cancelled);
  store.set(S.CANCELLED);
  toast(uz.toasts.cancelled);
}

async function startRecon() {
  const aoi = geometry();
  if (!aoi) {
    toast(uz.toasts.no_aoi, "warn");
    return;
  }
  clearResults();
  getMap().pm.disableDraw();
  store.set(S.RUNNING, { aoi });
  setProgress(0, uz.toasts.started);
  try {
    const res = await api.startRecon(aoi);
    store.patch({ runId: null, activeRunId: res.run_id });
    toast(uz.toasts.started);
    follow(res.run_id);
  } catch (e) {
    toast(e.message, "error", 6000);
    setProgress(0, e.message);
    store.set(S.ERROR);
  }
}

async function stopRecon() {
  const id = store.activeRunId;
  if (!id) return;
  $("btn-stop").disabled = true;
  try {
    await api.cancel(id);
  } catch (e) {
    toast(e.message, "error");
  }
  onCancelled();
}

// ---------------------------------------------------------------------------
// Ishga tushirish
// ---------------------------------------------------------------------------
function onAoi(geom) {
  const area = areaKm2(geom);
  $("area-badge").textContent = `${area.toFixed(2)} ${uz.common.km2}`;
  if (store.state === S.RUNNING) return;
  if (area > store.maxAoiKm2) toast(uz.toasts.aoi_too_large(store.maxAoiKm2), "warn");
  store.set(geom ? S.READY : S.IDLE, { aoi: geom, areaKm2: area });
}

function onMapClick(e) {
  if (store.state === S.RUNNING || !store.runId) return;
  if (getMap().pm.globalDrawModeEnabled()) return;
  openPixelPopup(getMap(), e.latlng, store.runId);
}

function onDate(ts) {
  setLayersDate(ts);
  setInfoDate(ts);
}

async function generateReport() {
  const id = store.runId;
  if (!id) return;
  reportGenerating();
  try {
    renderReport(await api.generateReport(id), id);
    toast(uz.toasts.report_ready);
  } catch (e) {
    toast(e.code === "REPORT_EXISTS" ? uz.report.exists : e.message, e.code === "REPORT_EXISTS" ? "info" : "error", 6000);
    let rep = null;
    try { rep = await api.report(id); } catch (_e) { rep = null; }
    renderReport(rep, id);
  }
}

async function restore() {
  try {
    const a = await api.active();
    if (a.active && a.run) {
      showAoi(a.run.aoi);
      store.patch({ aoi: a.run.aoi, areaKm2: a.run.area_km2 });
      $("area-badge").textContent = `${(a.run.area_km2 || 0).toFixed(2)} ${uz.common.km2}`;
      store.set(S.RUNNING, { activeRunId: a.run.id });
      setProgress(a.run.progress, `${a.run.stage}/10`);
      follow(a.run.id);
      return;
    }
  } catch (_e) { /* server javob bermadi */ }
  const last = recall();
  if (!last) return;
  try {
    const run = await api.run(last);
    if (run.status !== "completed") return;
    showAoi(run.aoi);
    store.patch({ aoi: run.aoi, areaKm2: run.area_km2 });
    $("area-badge").textContent = `${run.area_km2.toFixed(2)} ${uz.common.km2}`;
    store.set(S.DONE);
    await loadResults(last);
    setProgress(1, uz.states.done);
  } catch (_e) {
    remember(null);
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  applyI18n();
  initTabs();
  const map = initMap(onAoi, onMapClick);
  initOverlays(map);
  initLayersPanel();
  initDateSlider(onDate);
  initSettings((res) => store.patch({ maxAoiKm2: res.settings.max_aoi_km2 }));
  clearResults();

  $("btn-draw-rect").onclick = () => drawShape("rect");
  $("btn-draw-poly").onclick = () => drawShape("poly");
  $("btn-clear").onclick = () => {
    clearAoi();
    clearResults();
    remember(null);
    $("area-badge").textContent = `0.00 ${uz.common.km2}`;
    setProgress(0, "");
    store.set(S.IDLE, { aoi: null, areaKm2: 0 });
  };
  $("btn-recon").onclick = startRecon;
  $("btn-stop").onclick = stopRecon;
  $("btn-settings").onclick = openSettings;
  $("btn-report-gen").onclick = generateReport;
  $("btn-report-dl").onclick = downloadReport;

  store.on(updateUI);
  try {
    const s = await api.getSettings();
    store.patch({ maxAoiKm2: s.settings.max_aoi_km2 });
  } catch (_e) { /* standart chegarada qoladi */ }
  updateUI();
  await restore();
  repaginateAll();
});
