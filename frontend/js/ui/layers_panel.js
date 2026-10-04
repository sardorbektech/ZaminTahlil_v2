/**
 * Qatlamlar tabi: har bir qatlam — koʻrinish, shaffoflik, afsona, vaqt, manba va muallif
 * (qoidaviy formula / klassik ML / CV modeli — backend `producer` maydoni orqali, kelajakdagi modellar
 * avtomatik shu yerda chiqadi). Bir nechta qatlam bir vaqtda koʻrsatiladi. Band kompozitori: tabiiy,
 * soxta yoki maxsus R/G/B.
 *
 * Sana slayderi pozitsiyasi (pos) kasr boʻlishi mumkin: ikki haqiqiy sana orasida har bir qatlamning
 * ikkita kuzatuvi cross-fade qilinadi. Bir xil qatlam roʻyxati 2D overlaylar va 3D tekstura uchun ishlatiladi.
 */
import { api } from "../api/client.js";
import { uz } from "../i18n/uz.js";
import { clearOverlays, prefetch, setBlend } from "../map/overlays.js";
import { esc, flagBadge, h, num, pct } from "./format.js";
import { paginate } from "./paginate.js";

const STATIC_SENSORS = new Set(["Copernicus DEM", "SMAP L4"]);
const S2_BANDS = ["B2", "B3", "B4", "B5", "B8", "B8A", "B11", "B12"];
const PRESETS = { true: ["B4", "B3", "B2"], false: ["B8", "B4", "B3"] };
const DEFAULT_OPACITY = 0.85;
// Guruhlar tartibi (nomaʼlum guruhlar — masalan, yangi ML modellari — oxirida) va qatlam balandligi
const GROUP_ORDER = ["Optik", "Yer qoplami", "Indekslar", "Radar (SAR)", "Termal", "Relyef", "Tuproq namligi", "Oʻzgarishlar", "RGB xususiyatlari"];
const Z = { rgb: 1, false_color: 2, composite: 3, landcover: 40, confidence: 41, sar_water: 42, depressions: 43, class_change: 44 };
const zFor = (name) => Z[name] ?? 10;
const METHOD_BADGE = { rules: "rules", classic_ml: "ml", cv: "cv" };

const st = {
  runId: null,
  byName: new Map(),
  order: [],
  dates: [], // haqiqiy kuzatuv vaqtlari (slayder)
  pos: 0,
  visible: new Map(), // name -> opacity
  composite: { on: false, mode: "true", r: "B4", g: "B3", b: "B2", opacity: 1.0 },
  locked: false,
  lastCardKey: "",
  listeners: new Set(),
};

const host = () => document.getElementById("layers-pages");
const composerEl = () => document.getElementById("composer");

/** 3D koʻrinish qatlamlar oʻzgarganda qayta chizilishi uchun obuna. */
export function onLayersChanged(fn) {
  st.listeners.add(fn);
}

function notify() {
  st.listeners.forEach((fn) => fn());
}

export function resetLayers() {
  clearOverlays();
  Object.assign(st, { runId: null, byName: new Map(), order: [], dates: [], pos: 0, visible: new Map(), lastCardKey: "" });
  st.composite.on = false;
  renderComposer();
  paginate(host(), [h(`<div class="empty">${esc(uz.common.empty_run)}</div>`)]);
  updateToolbar();
  notify();
}

export function loadLayers(runId, layers, dates) {
  clearOverlays();
  st.runId = runId;
  st.byName = new Map();
  st.order = [];
  st.dates = dates.map((d) => d.time_ts);
  st.pos = Math.max(0, st.dates.length - 1);
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
  st.visible = new Map();
  if (st.byName.has("rgb")) st.visible.set("rgb", 1.0);
  if (st.byName.has("landcover")) st.visible.set("landcover", 0.7);
  renderComposer();
  render();
  sync();
}

/** Slayder pozitsiyasi (0 … n−1, kasr boʻlishi mumkin). */
export function setLayersPos(pos) {
  st.pos = pos;
  const key = cardKey();
  if (key !== st.lastCardKey) render(true); // kartalar faqat koʻrsatilgan kuzatuv almashganda yangilanadi
  sync();
}

export function setLayersLocked(locked) {
  st.locked = locked;
}

function instanceAt(name, ts) {
  const arr = st.byName.get(name) || [];
  if (!arr.length) return null;
  if (STATIC_SENSORS.has(arr[0].sensor) || ts === null || ts === undefined) return arr[arr.length - 1];
  let pick = null;
  for (const l of arr) if (l.acq_time_ts <= ts) pick = l;
  return pick;
}

function bracket() {
  const n = st.dates.length;
  if (!n) return { a: null, b: null, t: 0 };
  const i = Math.max(0, Math.min(n - 1, Math.floor(st.pos)));
  const j = Math.min(n - 1, i + 1);
  return { a: st.dates[i], b: st.dates[j], t: j === i ? 0 : st.pos - i };
}

/** Qatlam uchun aralashma: [{inst, weight}] (bir xil kuzatuv boʻlsa — bitta element). */
function blendFor(name) {
  const { a, b, t } = bracket();
  const A = instanceAt(name, a);
  const B = instanceAt(name, b);
  if (!A && !B) return [];
  if (A && B && A.id === B.id) return [{ inst: A, weight: 1 }];
  // "Ustiga" cross-fade: A toʻliq qoladi, B uning ustida 0 → 1 paydo boʻladi (oʻrtada xiralashish yoʻq).
  // Faqat bittasi boʻlsa — u sekin paydo boʻladi yoki yoʻqoladi.
  const out = [];
  if (A && t < 1) out.push({ inst: A, weight: B ? 1 : 1 - t });
  if (B && t > 0) out.push({ inst: B, weight: t });
  return out;
}

/** Kartada koʻrsatiladigan (eng yaqin) kuzatuv. */
function shownInstance(name) {
  const { a, b, t } = bracket();
  return instanceAt(name, t < 0.5 ? a : b) || instanceAt(name, a) || instanceAt(name, b);
}

function cardKey() {
  return st.order.map((n) => `${n}:${shownInstance(n)?.id ?? "-"}`).join("|");
}

function compositeItems() {
  const c = st.composite;
  if (!c.on) return [];
  return blendFor("rgb").map(({ inst, weight }) => ({
    id: `${inst.acq_time_ts}_${c.r}${c.g}${c.b}`,
    src: api.compositePath(st.runId, inst.acq_time_ts, c.r, c.g, c.b),
    weight,
  }));
}

/** Koʻrinadigan qatlamlar (z tartibida) — 2D va 3D uchun yagona manba. */
export function visibleStack() {
  const out = [];
  for (const [name, opacity] of st.visible) {
    const items = blendFor(name).map(({ inst, weight }) => ({ id: inst.id, src: inst.image_url, weight }));
    if (items.length) out.push({ key: name, z: zFor(name), opacity, items });
  }
  const ci = compositeItems();
  if (ci.length) out.push({ key: "composite", z: zFor("composite"), opacity: st.composite.opacity, items: ci });
  return out.sort((x, y) => x.z - y.z);
}

function updateToolbar() {
  const n = st.visible.size + (st.composite.on ? 1 : 0);
  const btn = document.getElementById("btn-layers-clear");
  if (btn && !st.locked) btn.disabled = n === 0;
  const cnt = document.getElementById("layers-count");
  if (cnt) cnt.textContent = st.order.length ? uz.layers.shown_count(n) : "";
}

/** Barcha belgilangan qatlamlarni (va kompozitni) bitta tugma bilan olib tashlaydi. */
export function clearAllLayers() {
  if (st.locked) return;
  st.visible.clear();
  st.composite.on = false;
  renderComposer();
  render(true);
  sync();
}

function sync() {
  updateToolbar();
  const stack = new Map(visibleStack().map((s) => [s.key, s]));
  for (const name of [...st.byName.keys(), "composite"]) {
    const s = stack.get(name);
    setBlend(name, s ? s.items : [], s ? s.opacity : 0, zFor(name));
  }
  notify();
}

/** Koʻrinadigan qatlamlarning barcha sanalardagi tasvirlarini oldindan yuklash. */
function prefetchVisible() {
  const srcs = [];
  for (const name of st.visible.keys()) (st.byName.get(name) || []).forEach((l) => srcs.push(l.image_url));
  prefetch(srcs);
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

function producerBadge(p) {
  if (!p) return "";
  const cls = METHOD_BADGE[p.method] || "rules";
  const label = uz.layers.methods[p.method] || p.method;
  return `<span class="method ${cls}" title="${esc(`${p.analyzer} ${p.version}`)}">${esc(label)}</span>`;
}

function layerCard(name) {
  const arr = st.byName.get(name);
  const inst = shownInstance(name);
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
      <span class="name">${esc(ref.label_uz)}</span></label>${producerBadge(ref.producer)}<span class="muted small">${esc(ref.sensor)}</span></div>
    <div class="layer-meta"><span>${esc(uz.common.time)}: ${when}</span><span class="mono">${esc(ref.dataset)}</span>${meta}</div>
    ${on && inst ? `<div class="layer-ctl"><span>${esc(uz.layers.opacity)}</span><input type="range" class="lo" data-name="${esc(name)}" min="0" max="1" step="0.05" value="${op}"></div>${legendHtml(inst.legend)}` : ""}
  </div>`);
}

function render(keepPage = false) {
  st.lastCardKey = cardKey();
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
  document.getElementById("btn-layers-clear").addEventListener("click", clearAllLayers);
  hst.addEventListener("change", (e) => {
    const el = e.target;
    if (st.locked || !el.classList.contains("lt")) return;
    const name = el.dataset.name;
    if (el.checked) st.visible.set(name, st.visible.get(name) ?? DEFAULT_OPACITY);
    else st.visible.delete(name);
    render(true);
    sync();
    prefetchVisible();
  });
  hst.addEventListener("input", (e) => {
    const el = e.target;
    if (st.locked || !el.classList.contains("lo")) return;
    st.visible.set(el.dataset.name, parseFloat(el.value));
    sync();
  });
  const cmp = composerEl();
  cmp.addEventListener("change", (e) => {
    if (st.locked) return;
    readComposer();
    if (e.target.id === "cmp-mode") renderComposer();
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

export { prefetchVisible };
