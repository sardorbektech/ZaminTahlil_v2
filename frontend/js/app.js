/**
 * ZaminTahlil v2 — Asosiy Frontend ilovasi (app.js).
 */

import {
  checkActiveRun,
  startRecon,
  cancelRecon,
  fetchReconLayers,
  fetchClassDistribution,
  fetchWeatherData,
  fetchSatellitesData,
  fetchAIReport,
  regenerateAIReport,
  fetchUsageSummary,
  fetchSettings,
  updateSettings,
} from "./api/client.js";
import { listenToReconEvents } from "./api/sse.js";
import { i18n } from "./i18n/uz.js";
import {
  initMap,
  drawShape,
  clearAoiLayer,
  getCurrentAoiLayer,
  getMapInstance,
} from "./map/leaflet_init.js";
import { addImageLayerToMap, removeAllOverlays, setLayerOpacity, toggleLayerVisibility } from "./map/overlays.js";
import { startScanAnimation, stopScanAnimation } from "./map/scan_animation.js";
import { AppState, stateManager } from "./state.js";
import { setupDateSlider } from "./ui/date_slider.js";
import { downloadReportAsFile, renderMarkdownReport } from "./ui/report_view.js";
import { initTabs } from "./ui/tabs.js";

let sseConnection = null;
let currentReportMarkdown = "";

document.addEventListener("DOMContentLoaded", async () => {
  initTabs();
  setupUIEventListeners();

  // 1. Xaritani ishga tushirish
  const map = initMap((geoJson, layer) => {
    // Hudud chizilganda
    const coords = geoJson.geometry.coordinates[0];
    const areaKm2 = calculatePolygonArea(coords);
    updateAreaBadge(areaKm2);

    if (areaKm2 > 100.0) {
      showToast(i18n.toasts.aoi_too_large);
      stateManager.setState(AppState.IDLE);
    } else {
      stateManager.setState(AppState.READY, { aoi: geoJson.geometry, areaKm2 });
    }
  });

  // 2. Holat o'zgarganda UI ni yangilash
  stateManager.subscribe(updateUIForState);

  // 3. Faol ish bor-yo'qligini tekshirish (Reload bo'lganda)
  try {
    const activeData = await checkActiveRun();
    if (activeData.active && activeData.run) {
      stateManager.setState(AppState.RUNNING, { runId: activeData.run.id, areaKm2: activeData.run.area_km2 });
      startProgressTracking(activeData.run.id);
    }
  } catch (e) {
    console.warn("Active run tekshirishda xato:", e);
  }
});

function setupUIEventListeners() {
  const btnRect = document.getElementById("btn-draw-rect");
  const btnPoly = document.getElementById("btn-draw-poly");
  const btnClear = document.getElementById("btn-clear");
  const btnRecon = document.getElementById("btn-recon");
  const btnStop = document.getElementById("btn-stop");
  const btnSettings = document.getElementById("btn-settings");

  btnRect?.addEventListener("click", () => drawShape("Rectangle"));
  btnPoly?.addEventListener("click", () => drawShape("Polygon"));

  btnClear?.addEventListener("click", () => {
    clearAoiLayer();
    removeAllOverlays(getMapInstance());
    updateAreaBadge(0);
    stateManager.setState(AppState.IDLE, { aoi: null, areaKm2: 0 });
  });

  btnRecon?.addEventListener("click", async () => {
    const aoi = stateManager.currentAoi;
    if (!aoi) {
      showToast(i18n.toasts.no_aoi);
      return;
    }

    try {
      stateManager.setState(AppState.RUNNING);
      const res = await startRecon(aoi);
      stateManager.setState(AppState.RUNNING, { runId: res.run_id });
      showToast(i18n.toasts.job_started);
      startProgressTracking(res.run_id);
    } catch (err) {
      showToast(err.message);
      stateManager.setState(AppState.ERROR);
    }
  });

  btnStop?.addEventListener("click", async () => {
    const runId = stateManager.currentRunId;
    if (runId) {
      await cancelRecon(runId);
      if (sseConnection) sseConnection.close();
      stopScanAnimation(getCurrentAoiLayer());
      removeAllOverlays(getMapInstance());
      showToast(i18n.toasts.job_cancelled);
      stateManager.setState(AppState.CANCELLED);
    }
  });

  // Sozlamalar modali
  btnSettings?.addEventListener("click", openSettingsModal);
  document.getElementById("btn-close-settings")?.addEventListener("click", closeSettingsModal);
  document.getElementById("btn-save-settings")?.addEventListener("click", saveSettingsForm);

  // Hisobot yuklab olish
  document.getElementById("btn-download-report")?.addEventListener("click", () => {
    if (currentReportMarkdown) {
      downloadReportAsFile(`ZaminTahlil_Hisobot_${stateManager.currentRunId}.md`, currentReportMarkdown);
    }
  });

  // Hisobotni qayta generatsiya qilish
  document.getElementById("btn-regen-report")?.addEventListener("click", async () => {
    const runId = stateManager.currentRunId;
    if (!runId) return;
    const reportBox = document.getElementById("report-content");
    reportBox.innerHTML = `<i>${i18n.report.generating}</i>`;
    try {
      const res = await regenerateAIReport(runId);
      currentReportMarkdown = res.content_md;
      renderMarkdownReport("report-content", currentReportMarkdown);
    } catch (e) {
      showToast("Hisobotni qayta tuzishda xatolik");
    }
  });
}

function updateUIForState({ state, areaKm2 }) {
  const isRunning = state === AppState.RUNNING;
  const isReady = state === AppState.READY;

  // Tugmalar blokirovkasi
  document.getElementById("btn-draw-rect").disabled = isRunning;
  document.getElementById("btn-draw-poly").disabled = isRunning;
  document.getElementById("btn-clear").disabled = isRunning;
  document.getElementById("btn-settings").disabled = isRunning;

  const btnRecon = document.getElementById("btn-recon");
  btnRecon.disabled = !isReady || isRunning;

  const btnStop = document.getElementById("btn-stop");
  btnStop.disabled = !isRunning;

  const progressContainer = document.getElementById("progress-container");
  if (isRunning) {
    progressContainer.style.display = "block";
    startScanAnimation(getCurrentAoiLayer());
  } else {
    progressContainer.style.display = "none";
    stopScanAnimation(getCurrentAoiLayer());
  }
}

function startProgressTracking(runId) {
  const progressBar = document.getElementById("progress-bar-fill");

  sseConnection = listenToReconEvents(
    runId,
    (eventData) => {
      const pct = (eventData.stage / eventData.total_stages) * 100;
      progressBar.style.width = `${pct}%`;

      if (eventData.message_uz === "Yangi sunʼiy yoʻldosh maʼlumoti yoʻq") {
        showToast(i18n.toasts.no_new_data);
      }

      if (eventData.stage === 10) {
        stateManager.setState(AppState.DONE, { runId });
        showToast(i18n.toasts.job_completed);
        loadReconResults(runId);
      }
    },
    (err) => {
      console.warn("SSE xatolik:", err);
    }
  );
}

async function loadReconResults(runId) {
  const map = getMapInstance();
  const aoiLayer = getCurrentAoiLayer();
  const bounds = aoiLayer ? aoiLayer.getBounds() : map.getBounds();

  // 1. Qatlamlarni yuklash
  try {
    const layers = await fetchReconLayers(runId);
    renderLayersTab(layers, bounds);
  } catch (e) {
    console.warn("Qatlamlarni yuklashda xato:", e);
  }

  // 2. Yer qoplami maydonlarini yuklash
  try {
    const classes = await fetchClassDistribution(runId);
    renderInfoTab(classes);
  } catch (e) {
    console.warn("Ma'lumotlarni yuklashda xato:", e);
  }

  // 3. Ob-havo
  try {
    const weather = await fetchWeatherData(runId);
    renderWeatherTab(weather);
  } catch (e) {
    console.warn("Ob-havoni yuklashda xato:", e);
  }

  // 4. Sun'iy yo'ldoshlar
  try {
    const satellites = await fetchSatellitesData(runId);
    renderSatellitesTab(satellites);
    // Slayderni sozlash
    const dateEntries = satellites.map((s) => ({
      label: s.acq_time_local,
      ts: s.acq_time_ts,
    }));
    setupDateSlider(dateEntries, (sel) => {
      console.log("Tanlangan sana:", sel);
    });
  } catch (e) {
    console.warn("Sun'iy yo'ldoshlarni yuklashda xato:", e);
  }

  // 5. Hisobot
  try {
    const rep = await fetchAIReport(runId);
    currentReportMarkdown = rep.content_md;
    renderMarkdownReport("report-content", currentReportMarkdown);
  } catch (e) {
    console.warn("Hisobotni yuklashda xato:", e);
  }

  // 6. Nazorat
  try {
    const usage = await fetchUsageSummary(runId);
    renderUsageTab(usage);
  } catch (e) {
    console.warn("Usage yuklashda xato:", e);
  }
}

function renderLayersTab(layers, bounds) {
  const container = document.getElementById("layers-list");
  container.innerHTML = "";
  const map = getMapInstance();

  const layerNamesUz = {
    1: "Tabiiy ranglar (RGB)",
    2: "NDVI (Vegetatsiya)",
    5: "NDWI (Suv indeksi)",
    11: "SAR VV polarizatsiya",
    15: "LST (Yer sirti harorati)",
    16: "Balandlik (DEM)",
    17: "Nishablik (Slope)",
    19: "Relyef soyasi (Hillshade)",
    22: "Yer qoplami (Landcover)",
  };

  layers.forEach((l) => {
    const nameUz = layerNamesUz[l.kind] || `Qatlam #${l.id}`;
    const div = document.createElement("div");
    div.className = "layer-item";
    div.innerHTML = `
      <div class="layer-header">
        <label style="display:flex; align-items:center; gap:6px; cursor:pointer;">
          <input type="checkbox" class="layer-toggle" data-id="${l.id}">
          <span class="layer-title">${nameUz}</span>
        </label>
        <span style="font-size:11px; color:#94a3b8;">${l.acq_time_local}</span>
      </div>
      <div class="layer-controls">
        <span style="font-size:11px;">Shaffoflik:</span>
        <input type="range" class="opacity-slider" data-id="${l.id}" min="0" max="1" step="0.05" value="0.85">
      </div>
    `;

    // Checkbox bosilganda xaritaga qo'shish/yashirish
    const toggle = div.querySelector(".layer-toggle");
    const slider = div.querySelector(".opacity-slider");

    toggle.addEventListener("change", (e) => {
      if (e.target.checked) {
        addImageLayerToMap(map, l.id, l.image_url, bounds, parseFloat(slider.value));
      } else {
        toggleLayerVisibility(map, l.id, false);
      }
    });

    slider.addEventListener("input", (e) => {
      setLayerOpacity(l.id, parseFloat(e.target.value));
    });

    container.appendChild(div);
  });
}

function renderInfoTab(classes) {
  const container = document.getElementById("info-content");
  if (!classes || classes.length === 0) {
    container.innerHTML = `<p style="color:#94a3b8;">${i18n.info.no_data}</p>`;
    return;
  }

  const rows = classes
    .map(
      (c) => `
    <tr>
      <td>${c.label_uz}</td>
      <td style="text-align:right;">${c.area_ha} ga</td>
      <td style="text-align:right;"><b>${c.pct}%</b></td>
    </tr>
  `
    )
    .join("");

  container.innerHTML = `
    <h4 style="margin-bottom:10px; color:#38bdf8;">${i18n.info.landcover_title}</h4>
    <table class="pixel-popup-table" style="width:100%;">
      <thead>
        <tr style="color:#94a3b8; font-size:11px;">
          <th style="text-align:left;">Sinf</th>
          <th style="text-align:right;">Maydon</th>
          <th style="text-align:right;">Ulush</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function renderWeatherTab(weather) {
  const container = document.getElementById("weather-content");
  const impacts = weather.impact_statements || [];

  const impactCards = impacts
    .map(
      (imp) => `
    <div style="background:#0f172a; border-left:3px solid #38bdf8; padding:8px 10px; margin-bottom:8px; border-radius:4px;">
      <div style="font-size:12px;">${imp.message_uz}</div>
    </div>
  `
    )
    .join("");

  container.innerHTML = `
    <h4 style="margin-bottom:10px; color:#38bdf8;">${i18n.weather.impact_title}</h4>
    ${impactCards || "<p style='color:#94a3b8;'>Ob-havo taʼsiri xulosalari mavjud emas</p>"}
  `;
}

function renderSatellitesTab(satellites) {
  const container = document.getElementById("satellites-content");
  const rows = satellites
    .map(
      (s) => `
    <tr>
      <td><b>${s.sensor_name}</b></td>
      <td style="font-family:monospace; font-size:11px;">${s.scene_id.substring(0, 18)}...</td>
      <td>${s.acq_time_local}</td>
      <td style="text-align:right;">${s.cloud_pct}%</td>
    </tr>
  `
    )
    .join("");

  container.innerHTML = `
    <h4 style="margin-bottom:10px; color:#38bdf8;">${i18n.satellites.title}</h4>
    <table class="pixel-popup-table" style="width:100%;">
      <thead>
        <tr style="color:#94a3b8; font-size:11px;">
          <th style="text-align:left;">Sensor</th>
          <th style="text-align:left;">Kadr</th>
          <th style="text-align:left;">Sana</th>
          <th style="text-align:right;">Bulut</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function renderUsageTab(usage) {
  const container = document.getElementById("usage-content");
  if (usage.markdown_report && window.marked) {
    container.innerHTML = window.marked.parse(usage.markdown_report);
  } else {
    container.innerHTML = `<pre style="font-size:11px; white-space:pre-wrap;">${JSON.stringify(usage, null, 2)}</pre>`;
  }
}

async function openSettingsModal() {
  const modal = document.getElementById("settings-modal");
  modal.style.display = "flex";
  try {
    const s = await fetchSettings();
    document.getElementById("input-lookback").value = s.lookback_days || 10;
    document.getElementById("input-max-cloud").value = s.max_scene_cloud_pct || 40;
    document.getElementById("input-resolution").value = s.analysis_resolution_m || 10;
  } catch (e) {
    console.warn(e);
  }
}

function closeSettingsModal() {
  document.getElementById("settings-modal").style.display = "none";
}

async function saveSettingsForm() {
  const lookback = parseInt(document.getElementById("input-lookback").value, 10);
  const cloud = parseFloat(document.getElementById("input-max-cloud").value);
  const res = parseFloat(document.getElementById("input-resolution").value);

  await updateSettings({
    lookback_days: lookback,
    max_scene_cloud_pct: cloud,
    analysis_resolution_m: res,
  });

  closeSettingsModal();
  showToast("Sozlamalar saqlandi");
}

function updateAreaBadge(km2) {
  const badge = document.getElementById("area-badge");
  if (badge) {
    badge.textContent = `${km2.toFixed(2)} km²`;
  }
}

function showToast(msg) {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = msg;
  container.appendChild(t);
  setTimeout(() => {
    if (t.parentNode) t.parentNode.removeChild(t);
  }, 3000);
}

function calculatePolygonArea(coords) {
  if (coords.length < 3) return 0;
  let area = 0;
  for (let i = 0; i < coords.length; i++) {
    const p1 = coords[i];
    const p2 = coords[(i + 1) % coords.length];
    const lon1 = (p1[0] * Math.PI) / 180;
    const lat1 = (p1[1] * Math.PI) / 180;
    const lon2 = (p2[0] * Math.PI) / 180;
    const lat2 = (p2[1] * Math.PI) / 180;
    area += (lon2 - lon1) * (2 + Math.sin(lat1) + Math.sin(lat2));
  }
  const areaM2 = Math.abs((area * 6378137 * 6378137) / 2);
  return areaM2 / 1000000;
}
