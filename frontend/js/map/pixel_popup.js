/**
 * Xarita bosilganda o'sha nuqtadagi (Pixel) barcha ko'rsatkichlarni popupda ko'rsatish.
 */

import { fetchPixelData } from "../api/client.js";

export async function handleMapClick(map, e, activeRunId) {
  if (!activeRunId) return;

  const lat = e.latlng.lat;
  const lon = e.latlng.lng;

  const popup = L.popup()
    .setLatLng(e.latlng)
    .setContent("<i>Nuqta maʼlumotlari olinmoqda...</i>")
    .openOn(map);

  try {
    const data = await fetchPixelData(activeRunId, lon, lat);
    const valRows = Object.entries(data.values || {})
      .map(
        ([k, v]) =>
          `<tr><td><b>${k.toUpperCase()}</b></td><td>${v !== null ? v : "maʼlumot yoʻq"}</td></tr>`
      )
      .join("");

    const content = `
      <div style="min-width: 220px;">
        <div style="font-weight: 700; color: #38bdf8; margin-bottom: 4px;">
          📍 ${data.landcover_label}
        </div>
        <div style="font-size: 11px; color: #94a3b8; margin-bottom: 6px;">
          Sana: ${data.timestamp_local}<br>
          Manba: ${data.source}
        </div>
        <table class="pixel-popup-table">
          ${valRows}
        </table>
      </div>
    `;
    popup.setContent(content);
  } catch (err) {
    popup.setContent("<span style='color: #ef4444;'>Maʼlumotni yuklab boʻlmadi</span>");
  }
}
