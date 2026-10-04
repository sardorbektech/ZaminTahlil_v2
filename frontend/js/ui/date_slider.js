/**
 * Pastki sana slayderi: faqat haqiqiy kuzatuv sanalari. Surish paytida pozitsiya kasr boʻladi va
 * qatlamlar ikki sana orasida silliq cross-fade qilinadi; qoʻyib yuborilganda eng yaqin haqiqiy sanaga
 * silliq (animatsiya bilan) oʻtadi. Oraliq "kadr" hisoblanmaydi — faqat ikki tasvir aralashadi.
 */
import { uz } from "../i18n/uz.js";

const SNAP_MS = 600;
let dates = [];
let onChange = null;
let anim = null;

const slider = () => document.getElementById("date-slider");
const label = () => document.getElementById("date-label");

function show(pos) {
  const n = dates.length;
  if (!n) {
    label().textContent = uz.bottom.no_dates;
    return;
  }
  const i = Math.floor(pos);
  const t = pos - i;
  const a = dates[Math.min(i, n - 1)];
  if (t > 0.02 && t < 0.98 && i + 1 < n) {
    label().textContent = `${a.time_local} → ${dates[i + 1].time_local}`;
  } else {
    const d = dates[Math.round(pos)];
    label().textContent = `${d.time_local} · ${d.sensors.join(", ")}`;
  }
}

function emit(pos) {
  show(pos);
  onChange?.(pos);
}

function snap() {
  const s = slider();
  const from = parseFloat(s.value);
  const to = Math.round(from);
  if (Math.abs(to - from) < 1e-3) {
    emit(to);
    return;
  }
  const t0 = performance.now();
  cancelAnimationFrame(anim);
  const step = (now) => {
    const k = Math.min(1, (now - t0) / SNAP_MS);
    const e = 1 - (1 - k) ** 3; // ease-out
    const v = from + (to - from) * e;
    s.value = String(v);
    emit(v);
    if (k < 1) anim = requestAnimationFrame(step);
  };
  anim = requestAnimationFrame(step);
}

export function initDateSlider(cb) {
  onChange = cb;
  const s = slider();
  s.step = "any";
  s.addEventListener("input", () => {
    cancelAnimationFrame(anim);
    emit(parseFloat(s.value));
  });
  s.addEventListener("change", snap);
}

export function setDates(list) {
  cancelAnimationFrame(anim);
  dates = list || [];
  const s = slider();
  s.min = "0";
  s.max = String(Math.max(0, dates.length - 1));
  s.value = s.max;
  s.disabled = dates.length < 2;
  show(dates.length - 1);
  return Math.max(0, dates.length - 1);
}

export function clearDates() {
  setDates([]);
}

/** Pozitsiyaga eng yaqin haqiqiy kuzatuv vaqti. */
export function nearestTs(pos) {
  const d = dates[Math.round(pos)];
  return d ? d.time_ts : null;
}
