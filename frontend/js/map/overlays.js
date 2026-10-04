/**
 * L.imageOverlay qatlamlari. Har bir qatlam nomi uchun bitta faol overlay; sana almashganda
 * eski va yangi tasvir orasida oddiy cross-fade. PNG lar blob sifatida olinadi va tozalashda
 * barcha object URL lar revoke qilinadi.
 */
import { api } from "../api/client.js";

const FADE_MS = 450;
const active = new Map(); // key -> {overlay, layerId, opacity}
const urls = new Map(); // src -> objectURL
let map = null;
let bounds = null;
let generation = 0; // tozalashdan keyin kechikkan yuklashlarni bekor qilish uchun

export function initOverlays(m) {
  map = m;
}

export function setBounds(b) {
  bounds = b;
}

async function objectUrl(src) {
  if (!urls.has(src)) urls.set(src, await api.imageUrl(src));
  return urls.get(src);
}

/** key nomli overlay ni src tasviriga almashtiradi (cross-fade bilan). */
export async function showOverlay(key, layerId, src, opacity, zIndex = 10) {
  if (!map || !bounds) return;
  const gen = generation;
  const cur = active.get(key);
  if (cur && cur.layerId === layerId) {
    cur.overlay.setOpacity(opacity);
    cur.opacity = opacity;
    return;
  }
  const url = await objectUrl(src);
  if (gen !== generation) return;
  const ov = L.imageOverlay(url, bounds, { opacity: 0, className: "zt-overlay", interactive: false, zIndex }).addTo(map);
  active.set(key, { overlay: ov, layerId, opacity });
  requestAnimationFrame(() => ov.setOpacity(opacity));
  if (cur) {
    cur.overlay.setOpacity(0);
    setTimeout(() => map.removeLayer(cur.overlay), FADE_MS);
  }
}

export function hideOverlay(key) {
  const cur = active.get(key);
  if (!cur) return;
  active.delete(key);
  cur.overlay.setOpacity(0);
  setTimeout(() => map.removeLayer(cur.overlay), FADE_MS);
}

export function setOverlayOpacity(key, opacity) {
  const cur = active.get(key);
  if (cur) {
    cur.opacity = opacity;
    cur.overlay.setOpacity(opacity);
  }
}

export function isShown(key) {
  return active.has(key);
}

/** Barcha overlaylarni olib tashlaydi va object URL larni boʻshatadi. */
export function clearOverlays() {
  generation += 1;
  active.forEach(({ overlay }) => map?.removeLayer(overlay));
  active.clear();
  urls.forEach((u) => URL.revokeObjectURL(u));
  urls.clear();
}
