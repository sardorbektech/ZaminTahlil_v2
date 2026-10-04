/**
 * Qatlamlar tabi: har bir qatlam — koʻrinish, shaffoflik, afsona, vaqt va manba.
 * Bir nechta qatlam bir vaqtda koʻrsatilishi mumkin. Band kompozitori: tabiiy, soxta yoki maxsus R/G/B.
 * Tanlangan sanada har bir qatlam oʻzining shu sanagacha boʻlgan eng soʻnggi haqiqiy kuzatuvini koʻrsatadi.
 */
import { api } from "../api/client.js";
import { uz } from "../i18n/uz.js";
import { clearOverlays, hideOverlay, setOverlayOpacity, showOverlay } from "../map/overlays.js";
import { esc, flagBadge, h, num, pct } from "./format.js";
import { paginate } from "./paginate.js";

const STATIC_SENSORS = new Set(["Copernicus DEM", "SMAP L4"]);
const S2_BANDS = ["B2", "B3", "B4", "B5", "B8", "B8A", "B11", "B12"];
const PRESETS = { true: ["B4", "B3", "B2"], false: ["B8", "B4", "B3"] };
const DEFAULT_OPACITY = 0.85;
// Guruhlar tartibi va xaritadagi qatlam balandligi (tasvirlar pastda, niqob/sinflar tepada)
const GROUP_ORDER = ["Optik", "Yer qoplami", "Indekslar", "Radar (SAR)", "Termal", "Relyef", "Tuproq namligi", "Oʻzgarishlar", "RGB xususiyatlari"];
const Z = { rgb: 1, false_color: 2, composite: 3, landcover: 40, confidence: 41, sar_water: 42, depressions: 43, class_change: 44 };
const zFor = (name) => Z[name] ?? 10;

const st = {
  runId: null,
  byName: new Map(),
  order: [],
  date: null,
  visible: new Map(), // name -> opacity
  composite: { on: false, mode: "true", r: "B4", g: "B3", b: "B2", opacity: 1.0 },
  locked: false,
};

const host = () => document.getElementById("layers-pages");
const composerEl = () => document.getElementById("composer");

export function resetLayers() {
  clearOverlays();
  st.runId = null;
  st.byName = new Map();
  st.order = [];
  st.visible = new Map();
  st.composite.on = false;
  st.date = null;
  renderComposer();
  paginate(host(), [h(`<div class="empty">${esc(uz.common.empty_run)}</div>`)]);
}

export function loadLayers(runId, layers) {
  clearOverlays();
  st.runId = runId;
  st.byName = new Map();
  st.order = [];
  for (const l of layers) {
    if (!st.byName.has(l.name)) {
      st.byName.set(l.name, []);
      st.order.push(l.name);
    }
    st.byName.get(l.name).push(l);
  }
  st.byName.forEach((arr) => arr.sort((a, b) => a.acq_time_ts - b.acq_time_ts));
  const gi = (n) => {
    const i = GROUP_ORDER.indexOf(st.byName.get(n)[0].group_uz);
    return i < 0 ? GROUP_ORDER.length : i;
  };
  st.order = st.order.map((n, i) => [n, i]).sort((a, b) => gi(a[0]) - gi(b[0]) || a[1] - b[1]).map((x) => x[0]);
  // Boshlang'ich: tabiiy rang va yer qoplami
  st.visible = new Map();
  if (st.byName.has("rgb")) st.visible.set("rgb", 1.0);
  if (st.byName.has("landcover")) st.visible.set("landcover", 0.7);
  renderComposer();
  render();
  sync();
}

export function setLayersDate(ts) {
  st.date = ts;
  render(true);
  sync();
}

export function setLayersLocked(locked) {
  st.locked = locked;
}

function instanceFor(name) {
  const arr = st.byName.get(name) || [];
  if (!arr.length) return null;
  if (STATIC_SENSORS.has(arr[0].sensor) || st.date === null) return arr[arr.length - 1];
  let pick = null;
  for (const l of arr) if (l.acq_time_ts <= st.date) pick = l;
  return pick;
}

function sync() {
  st.byName.forEach((_arr, name) => {
    const inst = instanceFor(name);
    if (st.visible.has(name) && inst) showOverlay(name, inst.id, inst.image_url, st.visible.get(name), zFor(name));
    else hideOverlay(name);
  });
  const rgb = instanceFor("rgb");
  if (st.composite.on && rgb) {
    const c = st.composite;
    const src = api.compositePath(st.runId, rgb.acq_time_ts, c.r, c.g, c.b);
    showOverlay("composite", `${rgb.acq_time_ts}_${c.r}${c.g}${c.b}`, src, c.opacity, zFor("composite"));
  } else {
    hideOverlay("composite");
  }
}

function legendHtml(lg) {
  if (!lg) return "";
  if (lg.type === "gradient") {
    const unit = lg.unit ? ` ${esc(lg.unit)}` : "";
    return `<div class="legend"><div class="bar" style="background:linear-gradient(90deg,${lg.stops.map(esc).join(",")})"></div>
      <div class="ends"><span>${esc(num(lg.min, 3))}${unit}</span><span>${esc(num(lg.max, 3))}${unit}</span></div></div>`;
  }
  if (lg.type === "classes") {
    return `<div class="legend"><div class="classes">${lg.items
      .map((i) => `<span><span class="swatch" style="background:${esc(i.color)}"></span>${esc(i.label_uz)}</span>`)
      .join("")}</div></div>`;
  }
  return `<div class="legend"><div class="ends"><span>${esc(lg.unit)}: ${esc(num(lg.min, 2))} – ${esc(num(lg.max, 2))}</span></div></div>`;
}

function layerCard(name) {
  const arr = st.byName.get(name);
  const inst = instanceFor(name);
  const ref = inst || arr[arr.length - 1];
  const on = st.visible.has(name);
  const op = st.visible.get(name) ?? DEFAULT_OPACITY;
  const when = inst
    ? `${esc(inst.acq_time_local)}${inst.prev_time_local ? ` (← ${esc(inst.prev_time_local)})` : ""}`
    : `<i>${esc(uz.layers.not_for_date)}</i>`;
  const meta = inst
    ? `<span>${esc(uz.common.valid)}: ${esc(pct(inst.valid_pct))}</span>${inst.cloud_masked_pct !== null ? `<span>${esc(uz.common.cloud)}: ${esc(pct(inst.cloud_masked_pct))}</span>` : ""}
       ${inst.stats && inst.stats.mean !== null ? `<span>${esc(uz.info.mean)}: ${esc(num(inst.stats.mean, 3, inst.unit))}</span>` : ""}${flagBadge(inst.quality_flag)}`
    : "";
  return h(`<div class="layer ${on ? "on" : ""}" data-name="${esc(name)}">
    <div class="layer-head"><label><input type="checkbox" class="lt" data-name="${esc(name)}" ${on ? "checked" : ""} ${inst ? "" : "disabled"}>
      <span class="name">${esc(ref.label_uz)}</span></label><span class="muted small">${esc(ref.sensor)}</span></div>
    <div class="layer-meta"><span>${esc(uz.common.time)}: ${when}</span><span class="mono">${esc(ref.dataset)}</span>${meta}</div>
    ${on && inst ? `<div class="layer-ctl"><span>${esc(uz.layers.opacity)}</span><input type="range" class="lo" data-name="${esc(name)}" min="0" max="1" step="0.05" value="${op}"></div>${legendHtml(inst.legend)}` : ""}
  </div>`);
}

function render(keepPage = false) {
  if (!st.order.length) {
    paginate(host(), [h(`<div class="empty">${esc(uz.layers.no_layers)}</div>`)]);
    return;
  }
  const nodes = [];
  let group = null;
  for (const name of st.order) {
    const g = st.byName.get(name)[0].group_uz;
    if (g !== group) {
      nodes.push(h(`<div class="layer-group">${esc(g)}</div>`));
      group = g;
    }
    nodes.push(layerCard(name));
  }
  paginate(host(), nodes, { keepPage });
}

function renderComposer() {
  const c = st.composite;
  const opts = (sel) => S2_BANDS.map((b) => `<option ${b === sel ? "selected" : ""}>${b}</option>`).join("");
  const has = st.byName.has("rgb");
  composerEl().innerHTML = `
    <div class="row"><strong class="small">${esc(uz.layers.composer)}</strong>
      <select id="cmp-mode" ${has ? "" : "disabled"}>
        <option value="true" ${c.mode === "true" ? "selected" : ""}>${esc(uz.layers.true_color)}</option>
        <option value="false" ${c.mode === "false" ? "selected" : ""}>${esc(uz.layers.false_color)}</option>
        <option value="custom" ${c.mode === "custom" ? "selected" : ""}>${esc(uz.layers.custom)}</option>
      </select></div>
    <div class="rgb">
      <select id="cmp-r" ${c.mode === "custom" && has ? "" : "disabled"}>${opts(c.r)}</select>
      <select id="cmp-g" ${c.mode === "custom" && has ? "" : "disabled"}>${opts(c.g)}</select>
      <select id="cmp-b" ${c.mode === "custom" && has ? "" : "disabled"}>${opts(c.b)}</select>
    </div>
    <button id="cmp-toggle" ${has ? "" : "disabled"}>${esc(c.on ? uz.layers.hide : uz.layers.show)}</button>`;
}

function readComposer() {
  const c = st.composite;
  c.mode = document.getElementById("cmp-mode").value;
  if (c.mode === "custom") {
    c.r = document.getElementById("cmp-r").value;
    c.g = document.getElementById("cmp-g").value;
    c.b = document.getElementById("cmp-b").value;
  } else {
    [c.r, c.g, c.b] = PRESETS[c.mode];
  }
}

export function initLayersPanel() {
  const hst = host();
  hst.addEventListener("change", (e) => {
    const el = e.target;
    if (st.locked || !el.classList.contains("lt")) return;
    const name = el.dataset.name;
    if (el.checked) st.visible.set(name, st.visible.get(name) ?? DEFAULT_OPACITY);
    else st.visible.delete(name);
    render(true);
    sync();
  });
  hst.addEventListener("input", (e) => {
    const el = e.target;
    if (st.locked || !el.classList.contains("lo")) return;
    const v = parseFloat(el.value);
    st.visible.set(el.dataset.name, v);
    setOverlayOpacity(el.dataset.name, v);
  });
  const cmp = composerEl();
  cmp.addEventListener("change", (e) => {
    if (st.locked) return;
    if (e.target.id === "cmp-mode") {
      readComposer();
      renderComposer();
    } else {
      readComposer();
    }
    if (st.composite.on) sync();
  });
  cmp.addEventListener("click", (e) => {
    if (st.locked || e.target.id !== "cmp-toggle") return;
    readComposer();
    st.composite.on = !st.composite.on;
    renderComposer();
    sync();
  });
  resetLayers();
}
