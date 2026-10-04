/** Koʻrsatish yordamchilari: HTML qochirish, sonlar va "maʼlumot yoʻq". Hisoblash yoʻq — faqat formatlash. */
import { uz } from "../i18n/uz.js";

export function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

/** Son yoki "maʼlumot yoʻq". */
export function num(v, digits = 2, unit = "") {
  if (v === null || v === undefined || Number.isNaN(v)) return uz.common.no_data;
  const s = Number(v).toLocaleString("uz-UZ", { maximumFractionDigits: digits, minimumFractionDigits: 0 });
  return unit ? `${s} ${unit}` : s;
}

export function pct(v, digits = 1) {
  return v === null || v === undefined ? uz.common.no_data : `${Number(v).toFixed(digits)}%`;
}

/** Sifat bayrogʻi nishoni. */
export function flagBadge(flag) {
  if (!flag || flag === "GOOD") return "";
  if (flag === "LOW_CONFIDENCE") return `<span class="flag low">${esc(uz.common.low_conf)}</span>`;
  if (flag === "NO_DATA") return `<span class="flag nodata">${esc(uz.common.no_data)}</span>`;
  return `<span class="flag cloud">${esc(uz.common.cloud)}</span>`;
}

export function h(html) {
  const tpl = document.createElement("template");
  tpl.innerHTML = html.trim();
  return tpl.content.firstElementChild;
}
