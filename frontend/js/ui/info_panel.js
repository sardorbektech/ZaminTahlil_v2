/** Maʼlumot tabi: hudud xulosasi, yer qoplami (tanlangan sana), relyef, oʻzgarishlar, namlik, taqqoslash, sifat. */
import { uz } from "../i18n/uz.js";
import { esc, flagBadge, h, num, pct } from "./format.js";
import { paginate } from "./paginate.js";

let data = null; // {run, classes, changes, sats}
let date = null;

const host = () => document.getElementById("info-pages");

export function resetInfo() {
  data = null;
  paginate(host(), [h(`<div class="empty">${esc(uz.common.empty_run)}</div>`)]);
}

export function loadInfo(d) {
  data = d;
  render();
}

export function setInfoDate(ts) {
  date = ts;
  if (data) render(true);
}

function classesFor() {
  const ds = data.classes?.dates || [];
  if (!ds.length) return null;
  if (date === null) return ds[ds.length - 1];
  let pick = ds[0];
  for (const d of ds) if (d.acq_time_ts <= date) pick = d;
  return pick;
}

function statRow(label, s, unit = "") {
  if (!s) return `<dt>${esc(label)}</dt><dd>${esc(uz.common.no_data)}</dd>`;
  return `<dt>${esc(label)}</dt><dd>${esc(num(s.mean, 2, unit))} <span class="muted small">(${esc(num(s.min, 1))} – ${esc(num(s.max, 1))})</span></dd>`;
}

function render(keepPage = false) {
  const { run, classes, changes, sats } = data;
  const summary = data.summary || {};
  const nodes = [];

  nodes.push(h(`<div class="section-title">${esc(uz.info.run)} #${esc(run.id)}</div>`));
  nodes.push(h(`<dl class="kv card">
    <dt>${esc(uz.info.area)}</dt><dd>${esc(num(run.area_km2, 3, uz.common.km2))}</dd>
    <dt>${esc(uz.info.created)}</dt><dd>${esc(run.created_at_local)}</dd>
    <dt>${esc(uz.info.resolution)}</dt><dd>${esc(num(run.resolution_m, 0, "m"))}</dd></dl>`));

  // Yer qoplami
  const cd = classesFor();
  nodes.push(h(`<div class="section-title">${esc(uz.info.landcover)}</div>`));
  if (!cd) {
    nodes.push(h(`<div class="empty">${esc(uz.common.no_data)}</div>`));
  } else {
    nodes.push(h(`<div class="muted small">${esc(uz.info.landcover_date)}: ${esc(cd.acq_time_local)} · ${esc(uz.info.classified)}: ${esc(pct(cd.classified_pct))}
      ${cd.low_confidence ? flagBadge("LOW_CONFIDENCE") : ""} · ${esc(uz.info.sar_used)}: ${esc(cd.sar_obs_time_local || uz.common.no_data)}</div>`));
    const rows = cd.classes
      .map((c) => `<tr><td><span class="swatch" style="background:${esc(c.color)}"></span>${esc(c.label_uz)}</td>
        <td class="num">${esc(num(c.area_ha, 2, uz.common.ha))}</td><td class="num">${esc(pct(c.pct))}</td>
        <td class="num">${esc(c.mean_confidence === null ? "—" : num(c.mean_confidence, 2))}</td></tr>`)
      .join("");
    nodes.push(h(`<table class="tbl"><thead><tr><th>${esc(uz.info.class)}</th><th class="num">${esc(uz.info.area_col)}</th>
      <th class="num">${esc(uz.info.share)}</th><th class="num">${esc(uz.info.conf)}</th></tr></thead><tbody>${rows}</tbody></table>`));
  }

  // Relyef
  const tr = summary.terrain || {};
  nodes.push(h(`<div class="section-title">${esc(uz.info.terrain)} <span class="muted small">(${esc(tr.elevation?.acq_time_local || "")})</span></div>`));
  nodes.push(h(`<dl class="kv card">${statRow(uz.info.elevation, tr.elevation, "m")}${statRow(uz.info.slope, tr.slope, "°")}
    ${statRow(uz.info.tri, tr.tri, "m")}<dt>${esc(uz.info.low_areas)}</dt><dd>${esc(pct(tr.low_area_pct, 2))}</dd></dl>`));

  // O'zgarishlar
  nodes.push(h(`<div class="section-title">${esc(uz.info.changes)}</div>`));
  const s2 = changes?.sentinel2 || [];
  const s1 = changes?.sentinel1 || [];
  if (!s2.length && !s1.length) nodes.push(h(`<div class="empty">${esc(uz.info.no_changes)}</div>`));
  for (const c of s2) {
    const d = (k) => c[k]?.mean;
    nodes.push(h(`<div class="card"><div class="small"><b>Sentinel-2</b> ${esc(c.prev_time_local)} → ${esc(c.time_local)}</div>
      <dl class="kv"><dt>ΔNDVI</dt><dd>${esc(num(d("delta_ndvi"), 3))}</dd><dt>ΔNDWI</dt><dd>${esc(num(d("delta_ndwi"), 3))}</dd>
      <dt>ΔNDMI</dt><dd>${esc(num(d("delta_ndmi"), 3))}</dd><dt>ΔNBR</dt><dd>${esc(num(d("delta_nbr"), 3))}</dd>
      <dt>${esc(uz.info.changed)}</dt><dd>${esc(pct(c.transitions?.changed_pct))}</dd></dl></div>`));
    const tr2 = (c.transitions?.transitions || []).slice(0, 12);
    if (tr2.length) {
      nodes.push(h(`<table class="tbl"><thead><tr><th>${esc(uz.info.transitions)}</th><th class="num">${esc(uz.info.share)}</th></tr></thead><tbody>
        ${tr2.map((t) => `<tr><td>${esc(t.from_label)} → ${esc(t.to_label)}</td><td class="num">${esc(pct(t.pct, 2))}</td></tr>`).join("")}</tbody></table>`));
    }
  }
  for (const c of s1) {
    nodes.push(h(`<div class="card small"><b>Sentinel-1</b> ${esc(c.prev_time_local)} → ${esc(c.time_local)}:
      ΔVV ${esc(uz.info.mean)} ${esc(num(c.delta_vv_db?.mean, 2, "dB"))}</div>`));
  }

  // Tuproq namligi
  const sm = summary.soil_moisture || {};
  const t = sm.trend || {};
  nodes.push(h(`<div class="section-title">${esc(uz.info.soil)}</div>`));
  nodes.push(h(`<dl class="kv card">
    <dt>0–5 sm (${esc(sm.surface?.acq_time_local || uz.common.no_data)})</dt><dd>${esc(num(sm.surface?.mean, 3, "m³/m³"))}</dd>
    <dt>${esc(uz.info.soil_trend)}</dt><dd>${t.available ? `${esc(num(t.first_m3m3, 3))} → ${esc(num(t.last_m3m3, 3))} (${esc(num(t.delta_m3m3, 3))})` : esc(uz.common.no_data)}</dd>
    ${t.available ? `<dt></dt><dd class="muted small">${esc(t.first_time_local)} → ${esc(t.last_time_local)}</dd>` : ""}</dl>`));

  // S2 ↔ Landsat
  nodes.push(h(`<div class="section-title">${esc(uz.info.cross_check)}</div>`));
  const cc = changes?.cross_check || [];
  if (!cc.length) nodes.push(h(`<div class="empty">${esc(uz.info.no_cross)}</div>`));
  for (const c of cc) nodes.push(h(`<div class="card small">${esc(c.s2_time_local)} ↔ ${esc(c.landsat_time_local)}: ${esc(c.message_uz)}</div>`));

  // Sifat
  nodes.push(h(`<div class="section-title">${esc(uz.info.quality)}</div>`));
  const obs = sats?.observations || [];
  nodes.push(h(`<table class="tbl"><thead><tr><th>${esc(uz.satellites.observations)}</th><th class="num">${esc(uz.common.valid)}</th><th class="num">${esc(uz.common.cloud)}</th><th></th></tr></thead><tbody>
    ${obs.map((o) => `<tr><td>${esc(o.sensor)} ${esc(o.obs_time_local)}</td><td class="num">${esc(pct(o.valid_pct))}</td>
      <td class="num">${esc(o.cloud_masked_pct === null ? "—" : pct(o.cloud_masked_pct))}</td><td>${flagBadge(o.quality_flag)}</td></tr>`).join("")}</tbody></table>`));
  paginate(host(), nodes, { keepPage });
}
