/** 2D xaritada yer qoplami nomlari (joriy sanadagi Sentinel-2 tasnifi boʻyicha, backend hisoblagan nuqtalarda). */
import { esc } from "../ui/format.js";

let group = null;
let on = true;

export function initLabels2d(map) {
  group = L.layerGroup().addTo(map);
}

export function setLabels2d(points) {
  if (!group) return;
  group.clearLayers();
  if (!on) return;
  for (const p of points || []) {
    const icon = L.divIcon({
      className: "label2d",
      html: `<span class="swatch" style="background:${esc(p.color)}"></span>${esc(p.label_uz)}`,
      iconSize: null,
    });
    L.marker([p.lat, p.lon], { icon, interactive: false, keyboard: false }).addTo(group);
  }
}

export function toggleLabels2d(value, points) {
  on = value;
  setLabels2d(points);
}

export function clearLabels2d() {
  group?.clearLayers();
}
