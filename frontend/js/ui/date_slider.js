/** Pastki sana slayderi: faqat haqiqiy kuzatuv sanalari (interpolatsiya qilingan kadrlar yoʻq). */
import { uz } from "../i18n/uz.js";

let dates = [];
let onChange = null;

const slider = () => document.getElementById("date-slider");
const label = () => document.getElementById("date-label");

function show(i) {
  const d = dates[i];
  label().textContent = d ? `${d.time_local} · ${d.sensors.join(", ")}` : uz.bottom.no_dates;
}

export function initDateSlider(cb) {
  onChange = cb;
  slider().addEventListener("input", () => {
    const i = parseInt(slider().value, 10);
    show(i);
    onChange?.(dates[i]?.time_ts ?? null);
  });
}

export function setDates(list) {
  dates = list || [];
  const s = slider();
  s.min = "0";
  s.max = String(Math.max(0, dates.length - 1));
  s.value = s.max;
  s.disabled = dates.length < 2;
  show(dates.length - 1);
  return dates.length ? dates[dates.length - 1].time_ts : null;
}

export function clearDates() {
  setDates([]);
}
