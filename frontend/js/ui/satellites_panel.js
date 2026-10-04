/** Sunʼiy yoʻldoshlar tabi: har bir manba nima berdi va qachon (kuzatuvlar, kadrlar, bandlar, sifat). */
import { uz } from "../i18n/uz.js";
import { esc, flagBadge, h, num, pct } from "./format.js";
import { paginate } from "./paginate.js";

const host = () => document.getElementById("satellites-pages");

export function resetSatellites() {
  paginate(host(), [h(`<div class="empty">${esc(uz.common.empty_run)}</div>`)]);
}

export function loadSatellites(d) {
  const nodes = [h(`<div class="section-title">${esc(uz.satellites.title)}</div>`)];
  const obsQ = new Map((d.observations || []).map((o) => [`${o.sensor}|${o.obs_time_ts}`, o]));
  for (const s of d.sources) {
    const obs = s.observations || [];
    const list = obs.length
      ? obs.map((o) => {
          const t = o.obs_time_local || o.acq_time_local;
          const q = obsQ.get(`${s.sensor}|${o.obs_time_ts}`);
          const qtxt = q ? ` · ${esc(uz.common.valid)} ${esc(pct(q.valid_pct))}${q.cloud_masked_pct !== null ? `, ${esc(uz.common.cloud)} ${esc(pct(q.cloud_masked_pct))}` : ""} ${flagBadge(q.quality_flag)}` : "";
          return `<li>${esc(t)}${qtxt}</li>`;
        }).join("")
      : `<li class="muted">${esc(uz.satellites.none)}</li>`;
    nodes.push(h(`<div class="card"><div><b>${esc(s.sensor)}</b> <span class="muted small">${esc(s.observation_count)} ${esc(uz.satellites.observations.toLowerCase())}</span></div>
      <div class="small mono">${esc((s.datasets || []).join(", ") || uz.common.no_data)}</div>
      <div class="small muted">${esc(uz.satellites.bands)}: ${esc((s.bands || []).join(", "))}</div>
      ${s.time_range_local ? `<div class="small muted">${esc(s.time_range_local.join(" – "))}</div>` : ""}
      <ul class="small" style="padding-left:16px">${list}</ul></div>`));
  }
  nodes.push(h(`<div class="section-title">${esc(uz.satellites.scenes)}</div>`));
  nodes.push(h(`<table class="tbl"><thead><tr><th>${esc(uz.satellites.scene_id)}</th><th>${esc(uz.satellites.acq)}</th><th class="num">${esc(uz.satellites.meta_cloud)}</th></tr></thead><tbody>
    ${d.scenes.map((s) => `<tr><td><div>${esc(s.platform)}${s.orbit_pass ? ` · ${esc(s.orbit_pass)}` : ""}</div><div class="mono" style="word-break:break-all">${esc(s.scene_id)}</div></td>
      <td>${esc(s.acq_time_local)}</td><td class="num">${esc(s.cloud_pct === null ? "—" : num(s.cloud_pct, 1, "%"))}</td></tr>`).join("")}</tbody></table>`));
  paginate(host(), nodes);
}
