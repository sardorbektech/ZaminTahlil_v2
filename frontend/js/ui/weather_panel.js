/** Ob-havo tabi: oʻtgan va prognoz qiymatlar (manba bilan), grafik, kunlik yogʻin va taʼsir xulosalari. */
import { uz } from "../i18n/uz.js";
import { esc, h, num } from "./format.js";
import { paginate } from "./paginate.js";

const host = () => document.getElementById("weather-pages");
const SRC_COLOR = { era5: "#38bdf8", gfs_analysis: "#a78bfa", gfs_forecast: "#f59e0b", chirps: "#22c55e" };
const MAX_LINK_GAP_S = 3 * 3600; // nuqtalar faqat yaqin boʻlsa chiziq bilan ulanadi (interpolatsiya yoʻq)

export function resetWeather() {
  paginate(host(), [h(`<div class="empty">${esc(uz.common.empty_run)}</div>`)]);
}

function chart(recs, nowTs) {
  const W = 370, H = 150, L = 28, R = 26, T = 8, B = 18;
  const pts = recs.filter((r) => r.time_ts);
  if (!pts.length) return `<div class="empty">${esc(uz.common.no_data)}</div>`;
  const t0 = pts[0].time_ts, t1 = pts[pts.length - 1].time_ts;
  const temps = pts.map((r) => r.temp_c).filter((v) => v !== null);
  const pr = pts.map((r) => r.precip_mm).filter((v) => v !== null);
  const tmin = Math.floor(Math.min(...temps, 0)), tmax = Math.ceil(Math.max(...temps, 1));
  const pmax = Math.max(1, ...pr);
  const x = (t) => L + ((t - t0) / Math.max(1, t1 - t0)) * (W - L - R);
  const yT = (v) => T + (1 - (v - tmin) / Math.max(1, tmax - tmin)) * (H - T - B);
  const yP = (v) => H - B - (v / pmax) * (H - T - B) * 0.6;
  let bars = "", line = "", dots = "";
  let prev = null;
  for (const r of pts) {
    const c = SRC_COLOR[r.source] || "#999";
    if (r.precip_mm !== null && r.precip_mm > 0) {
      bars += `<rect x="${x(r.time_ts) - 1}" y="${yP(r.precip_mm)}" width="2.2" height="${H - B - yP(r.precip_mm)}" fill="#22d3ee" opacity=".7"/>`;
    }
    if (r.temp_c !== null) {
      dots += `<circle cx="${x(r.time_ts)}" cy="${yT(r.temp_c)}" r="1.4" fill="${c}"/>`;
      if (prev && r.time_ts - prev.time_ts <= MAX_LINK_GAP_S && prev.source === r.source) {
        line += `<line x1="${x(prev.time_ts)}" y1="${yT(prev.temp_c)}" x2="${x(r.time_ts)}" y2="${yT(r.temp_c)}" stroke="${c}" stroke-width="1"/>`;
      }
      prev = r;
    }
  }
  const nowX = nowTs >= t0 && nowTs <= t1 ? `<line x1="${x(nowTs)}" x2="${x(nowTs)}" y1="${T}" y2="${H - B}" stroke="#e2e8f0" stroke-dasharray="3 3"/>
    <text x="${x(nowTs) + 3}" y="${T + 9}" fill="#e2e8f0" font-size="9">${esc(uz.weather.now)}</text>` : "";
  const fmtD = (ts) => new Date(ts * 1000).toLocaleDateString("uz-UZ", { timeZone: "Asia/Tashkent", day: "2-digit", month: "2-digit" });
  return `<svg class="wx-chart" viewBox="0 0 ${W} ${H}">
    <text x="2" y="${T + 6}" fill="#8d9bb5" font-size="9">${tmax}°</text><text x="2" y="${H - B}" fill="#8d9bb5" font-size="9">${tmin}°</text>
    <text x="${W - R + 2}" y="${T + 6}" fill="#22d3ee" font-size="9">${num(pmax, 1)}mm</text>
    ${bars}${line}${dots}${nowX}
    <text x="${L}" y="${H - 4}" fill="#8d9bb5" font-size="9">${esc(fmtD(t0))}</text>
    <text x="${W - R}" y="${H - 4}" fill="#8d9bb5" font-size="9" text-anchor="end">${esc(fmtD(t1))}</text>
  </svg>`;
}

function block(title, b) {
  if (!b || !b.available) return `<div class="card small"><b>${esc(title)}</b>: ${esc(uz.common.no_data)}</div>`;
  const src = b.sources.map((s) => uz.weather.sources_map[s] || s).join(", ");
  const ext = (e, unit) => (e ? `${esc(num(e.value, 1, unit))} <span class="muted small">(${esc(e.time_local)}, ${esc(uz.weather.sources_map[e.source] || e.source)})</span>` : esc(uz.common.no_data));
  return `<div class="card"><div class="small"><b>${esc(title)}</b> ${esc(b.from_local)} – ${esc(b.to_local)} · ${esc(src)}</div>
    <dl class="kv"><dt>${esc(uz.weather.precip)} (${esc(uz.weather.total)})</dt><dd>${esc(num(b.precip_total_mm, 1, "mm"))}</dd>
    <dt>${esc(uz.weather.temp)} min</dt><dd>${ext(b.temp_min_c, "°C")}</dd><dt>${esc(uz.weather.temp)} max</dt><dd>${ext(b.temp_max_c, "°C")}</dd>
    <dt>${esc(uz.weather.wind)} max</dt><dd>${ext(b.wind_max_ms, "m/s")}</dd></dl></div>`;
}

export function loadWeather(w) {
  const all = [...w.past, ...w.forecast].sort((a, b) => a.time_ts - b.time_ts);
  const nodes = [];
  const s = w.summary || {};
  nodes.push(h(`<div class="section-title">${esc(uz.weather.chart)}</div>`));
  nodes.push(h(`<div>${chart(all, Math.floor(Date.now() / 1000))}<div class="small muted">${Object.entries(SRC_COLOR)
    .map(([k, c]) => `<span><span class="swatch" style="background:${c}"></span>${esc(uz.weather.sources_map[k])}</span>`).join(" ")}</div></div>`));
  nodes.push(h(block(uz.weather.past, s.past)));
  nodes.push(h(block(uz.weather.forecast, s.forecast)));
  nodes.push(h(`<div class="small muted">${esc(uz.weather.gfs_run)}: ${esc(s.forecast?.gfs_run_local || uz.common.no_data)} ·
    ${esc(uz.weather.era5_last)}: ${esc(s.era5_last?.time_local || uz.common.no_data)}</div>`));
  for (const n of s.notes_uz || []) nodes.push(h(`<div class="small muted">${esc(n)}</div>`));

  nodes.push(h(`<div class="section-title">${esc(uz.weather.impact)}</div>`));
  for (const i of w.impact || []) {
    nodes.push(h(`<div class="card impact ${esc(i.severity)} small">${esc(i.message_uz)}</div>`));
  }

  const daily = [
    ...(s.past?.daily_precip || []),
    ...(s.forecast?.daily_precip || []),
    ...(s.chirps_daily || []),
  ];
  nodes.push(h(`<div class="section-title">${esc(uz.weather.daily)}</div>`));
  nodes.push(h(`<table class="tbl"><thead><tr><th>${esc(uz.weather.day)}</th><th>${esc(uz.common.source)}</th><th class="num">${esc(uz.weather.precip)}</th></tr></thead><tbody>
    ${daily.length ? daily.map((d) => `<tr><td>${esc(d.day_local)}</td><td>${esc(uz.weather.sources_map[d.source] || d.source)}</td><td class="num">${esc(num(d.precip_mm, 1, "mm"))}</td></tr>`).join("")
      : `<tr><td colspan="3">${esc(uz.common.no_data)}</td></tr>`}</tbody></table>`));

  nodes.push(h(`<div class="section-title">${esc(uz.weather.sources)}</div>`));
  nodes.push(h(`<dl class="kv card small">${Object.entries(w.datasets || {}).map(([k, v]) => `<dt>${esc(uz.weather.sources_map[k] || k)}</dt><dd class="mono">${esc(v)}</dd>`).join("")}</dl>`));
  paginate(host(), nodes);
}
