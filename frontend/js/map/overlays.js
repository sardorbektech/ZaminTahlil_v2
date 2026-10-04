/**
 * L.imageOverlay qatlamlari va sanalar orasidagi silliq oʻtish.
 *
 * Har bir qatlam kaliti uchun bir vaqtda ikkita haqiqiy kuzatuv tasviri boʻlishi mumkin:
 * slayder ikki sana orasida boʻlsa, A tasvir (1 − t), B tasvir t ogʻirlik bilan koʻrsatiladi —
 * bu oddiy cross-fade (oraliq qiymat hisoblanmaydi). PNG lar blob sifatida olinadi va tozalashda
 * barcha object URL lar revoke qilinadi.
 */
import { api } from "../api/client.js";

const FADE_MS = 350;
const pool = new Map(); // key -> Map(id -> {overlay})
const urls = new Map(); // src -> objectURL
const images = new Map(); // src -> Promise<HTMLImageElement> (3D tekstura uchun)
let map = null;
let bounds = null;
let generation = 0;

export function initOverlays(m) {
  map = m;
}

export function setBounds(b) {
  bounds = b;
}

export async function objectUrl(src) {
  if (!urls.has(src)) urls.set(src, api.imageUrl(src));
  return urls.get(src);
}

/** Yuklangan va dekodlangan tasvir (2D overlay va 3D tekstura uchun umumiy kesh). */
export function loadImage(src) {
  if (!images.has(src)) {
    images.set(
      src,
      objectUrl(src).then(
        (u) =>
          new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = () => resolve(img);
            img.onerror = reject;
            img.src = u;
          }),
      ),
    );
  }
  return images.get(src);
}

/** Oldindan yuklash: sana surilganda tasvirlar darhol tayyor boʻlsin. */
export function prefetch(srcs) {
  srcs.forEach((s) => loadImage(s).catch(() => {}));
}

/**
 * key qatlamini berilgan tasvirlar aralashmasi bilan koʻrsatadi.
 * @param {string} key
 * @param {{id: string|number, src: string, weight: number}[]} items 0–2 ta element (pastdan yuqoriga tartibda)
 * @param {number} opacity umumiy shaffoflik
 * @param {number} zIndex
 */
export async function setBlend(key, items, opacity, zIndex = 10) {
  if (!map || !bounds) return;
  const gen = generation;
  if (!pool.has(key)) pool.set(key, new Map());
  const entries = pool.get(key);
  const wanted = new Set(items.map((i) => String(i.id)));
  for (const it of items) {
    const id = String(it.id);
    if (!entries.has(id)) {
      const url = (await loadImage(it.src)).src;
      if (gen !== generation) return;
      if (entries.has(id)) continue;
      const ov = L.imageOverlay(url, bounds, { opacity: 0, className: "zt-overlay", interactive: false, zIndex }).addTo(map);
      entries.set(id, { overlay: ov });
    }
  }
  if (gen !== generation) return;
  // Roʻyxatdagi tartib = chizish tartibi: keyingi (yangi sana) tasvir oldingisining ustida
  items.forEach((it, k) => {
    const ov = entries.get(String(it.id))?.overlay;
    if (!ov) return;
    ov.setZIndex(zIndex * 2 + k);
    ov.setOpacity(opacity * it.weight);
  });
  for (const [id, e] of entries) {
    if (wanted.has(id)) continue;
    entries.delete(id);
    e.overlay.setOpacity(0);
    setTimeout(() => map.removeLayer(e.overlay), FADE_MS);
  }
}

export function hideOverlay(key) {
  setBlend(key, [], 0);
}

/** Barcha overlaylarni olib tashlaydi va object URL larni boʻshatadi. */
export function clearOverlays() {
  generation += 1;
  pool.forEach((entries) => entries.forEach(({ overlay }) => map?.removeLayer(overlay)));
  pool.clear();
  const pending = Array.from(urls.values());
  urls.clear();
  images.clear();
  pending.forEach((p) => p.then((u) => URL.revokeObjectURL(u)).catch(() => {}));
}

/** 2D overlaylarni vaqtincha yashirish (3D rejimda) yoki qayta koʻrsatish. */
export function setOverlaysHidden(hidden) {
  pool.forEach((entries) => entries.forEach(({ overlay }) => overlay.getElement()?.style.setProperty("visibility", hidden ? "hidden" : "")));
}
