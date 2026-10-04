/**
 * 3D koʻrinish (Three.js): relyef — Copernicus DEM balandliklari. Standart holatda AOI atrofi bilan (har tomondan
 * kamida 1.5 km, DEM asl aniqligi ~30 m), «Faqat maydon» rejimida — faqat tahlil to'ri. Sirt teksturasi — Esri World
 * Imagery + 2D dagi aynan oʻsha koʻrinadigan qatlamlar (ular faqat AOI to'ri ustida chiziladi; shaffoflik, tartib,
 * sanalar orasidagi cross-fade bilan). Balandlik koʻpaytmasi 1× — haqiqiy masshtab. Yer qoplami nomlari — 3D yorliqlar.
 * Boshqaruv: sichqoncha bilan erkin aylantirish, surish, yaqinlashtirish. Bosilgan nuqta qiymatlari yon panelda.
 */
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DObject, CSS2DRenderer } from "three/addons/renderers/CSS2DRenderer.js";
import { api } from "../api/client.js";
import { uz } from "../i18n/uz.js";
import { esc } from "../ui/format.js";
import { loadImage } from "./overlays.js";
import { fetchPixelInto } from "./pixel_popup.js";

const TEX_LIMIT = 4096;
const MAX_TILES = 144; // Esri plitkalari soni chegarasi (12×12)
const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile";

const S = {
  runId: null,
  open: false,
  data: null, // terrain3d javobi
  heights: null, // Float32Array
  exag: 1,
  scope: "context", // "context" — atrof bilan, "aoi" — faqat maydon
  cache: {}, // scope -> terrain3d javobi
  renderer: null,
  labelRenderer: null,
  scene: null,
  camera: null,
  controls: null,
  mesh: null,
  outline: null,
  canvas: null,
  ctx: null,
  texture: null,
  base: null, // Esri tasviri chizilgan canvas (yoki null)
  labelGroup: null,
  labelsOn: true,
  getStack: () => [],
  getLabels: () => [],
  pending: false,
  raf: 0,
  resizeObs: null,
};

const el = () => document.getElementById("view3d");

// ---------------------------------------------------------------------------
// Proyeksiya: grid EPSG:3857 da chiziqli, shuning uchun tekstura va to'r bir xil koordinatada
// ---------------------------------------------------------------------------
const R = 6378137;
const mx = (lon) => (lon * Math.PI * R) / 180;
const my = (lat) => R * Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));

function frac(lon, lat) {
  const [[s, w], [n, e]] = S.data.bounds_latlon;
  return { u: (mx(lon) - mx(w)) / (mx(e) - mx(w)), v: (my(n) - my(lat)) / (my(n) - my(s)) };
}

function heightAt(u, v) {
  const { width: W, height: H, min_m } = S.data;
  const x = Math.max(0, Math.min(W - 1, u * (W - 1)));
  const y = Math.max(0, Math.min(H - 1, v * (H - 1)));
  const x0 = Math.floor(x), y0 = Math.floor(y), x1 = Math.min(W - 1, x0 + 1), y1 = Math.min(H - 1, y0 + 1);
  const g = (i, j) => S.heights[j * W + i];
  const tx = x - x0, ty = y - y0;
  const hgt = g(x0, y0) * (1 - tx) * (1 - ty) + g(x1, y0) * tx * (1 - ty) + g(x0, y1) * (1 - tx) * ty + g(x1, y1) * tx * ty;
  return (hgt - min_m) * S.exag;
}

function local(u, v) {
  return new THREE.Vector3((u - 0.5) * S.data.size_x_m, heightAt(u, v), (v - 0.5) * S.data.size_y_m);
}

// ---------------------------------------------------------------------------
// Tekstura
// ---------------------------------------------------------------------------
async function buildBase() {
  // Esri plitkalarini chegaralarga moslab bitta canvasga yigʻish (CORS ruxsat etmasa — asos yoʻq)
  const [[s, w], [n, e]] = S.data.bounds_latlon;
  const cw = S.canvas.width, ch = S.canvas.height;
  const spanM = mx(e) - mx(w);
  let z = Math.max(1, Math.min(19, Math.round(Math.log2(((2 * Math.PI * R) / spanM) * (cw / 256)))));
  const tilesAt = (zz) => {
    const n = 2 ** zz, f = (x) => ((x + Math.PI * R) / (2 * Math.PI * R)) * n;
    const g = (y) => ((Math.PI * R - y) / (2 * Math.PI * R)) * n;
    return (Math.floor(f(mx(e))) - Math.floor(f(mx(w))) + 1) * (Math.floor(g(my(s))) - Math.floor(g(my(n))) + 1);
  };
  while (z > 1 && tilesAt(z) > MAX_TILES) z -= 1;
  const N = 2 ** z;
  const tx = (x) => ((x + Math.PI * R) / (2 * Math.PI * R)) * N;
  const ty = (y) => ((Math.PI * R - y) / (2 * Math.PI * R)) * N;
  const x0 = tx(mx(w)), x1 = tx(mx(e)), y0 = ty(my(n)), y1 = ty(my(s));
  const base = document.createElement("canvas");
  base.width = cw;
  base.height = ch;
  const bctx = base.getContext("2d");
  const jobs = [];
  for (let X = Math.floor(x0); X <= Math.floor(x1); X++) {
    for (let Y = Math.floor(y0); Y <= Math.floor(y1); Y++) {
      jobs.push(new Promise((resolve) => {
        const img = new Image();
        img.crossOrigin = "anonymous";
        img.onload = () => {
          bctx.drawImage(img, ((X - x0) / (x1 - x0)) * cw, ((Y - y0) / (y1 - y0)) * ch, (cw / (x1 - x0)) + 0.5, (ch / (y1 - y0)) + 0.5);
          resolve(true);
        };
        img.onerror = () => resolve(false);
        img.src = `${ESRI}/${z}/${Y}/${X}`;
      }));
    }
  }
  const ok = await Promise.all(jobs);
  try {
    bctx.getImageData(0, 0, 1, 1); // CORS tekshiruvi: "ifloslangan" canvas WebGL ga yuklanmaydi
  } catch (_e) {
    return null;
  }
  return ok.some(Boolean) ? base : null;
}

async function paint() {
  S.pending = false;
  if (!S.open || !S.ctx) return;
  const stack = S.getStack();
  const imgs = await Promise.all(stack.flatMap((l) => l.items.map((it) => loadImage(it.src).then((img) => ({ img, a: l.opacity * it.weight })).catch(() => null))));
  const { ctx, canvas } = S;
  ctx.globalAlpha = 1;
  ctx.fillStyle = "#3b4252";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  if (S.base) ctx.drawImage(S.base, 0, 0);
  // Qatlam PNG lari AOI to'ri chegarasida — atrof rejimida teksturaning shu qismiga chiziladi
  const [[gs, gw], [gn, ge]] = S.data.aoi_grid_bounds_latlon || S.data.bounds_latlon;
  const a = frac(gw, gn), b = frac(ge, gs);
  const dx = a.u * canvas.width, dy = a.v * canvas.height;
  const dw = (b.u - a.u) * canvas.width, dh = (b.v - a.v) * canvas.height;
  for (const x of imgs) {
    if (!x || x.a <= 0) continue;
    ctx.globalAlpha = Math.min(1, x.a);
    ctx.imageSmoothingEnabled = false; // sinf chegaralari xiralashmasin
    ctx.drawImage(x.img, dx, dy, dw, dh);
  }
  ctx.globalAlpha = 1;
  ctx.imageSmoothingEnabled = true;
  S.texture.needsUpdate = true;
}

/** Qatlamlar yoki sana oʻzgarganda chaqiriladi (bir kadrda bir marta qayta chiziladi). */
export function refresh3d() {
  if (!S.open || S.pending) return;
  S.pending = true;
  requestAnimationFrame(() => {
    paint();
    renderLabels();
  });
}

// ---------------------------------------------------------------------------
// Geometriya, yorliqlar, AOI chegarasi
// ---------------------------------------------------------------------------
function applyHeights() {
  const pos = S.mesh.geometry.attributes.position;
  const { width: W, min_m } = S.data;
  for (let i = 0; i < pos.count; i++) pos.setY(i, (S.heights[i] - min_m) * S.exag);
  pos.needsUpdate = true;
  S.mesh.geometry.computeVertexNormals();
  S.mesh.geometry.computeBoundingSphere();
  void W;
}

function buildOutline() {
  if (S.outline) S.scene.remove(S.outline);
  const ring = S.data.aoi.coordinates[0];
  const pts = [];
  for (let i = 0; i < ring.length - 1; i++) {
    const a = frac(...ring[i]), b = frac(...ring[i + 1]);
    for (let k = 0; k <= 24; k++) {
      const u = a.u + (b.u - a.u) * (k / 24), v = a.v + (b.v - a.v) * (k / 24);
      const p = local(u, v);
      p.y += 2 * S.exag + 1;
      pts.push(p);
    }
  }
  S.outline = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: 0x38bdf8 }));
  S.scene.add(S.outline);
}

function renderLabels() {
  if (!S.labelGroup) return;
  S.labelGroup.children.slice().forEach((o) => {
    S.labelGroup.remove(o);
    o.element?.remove();
  });
  if (!S.labelsOn) return;
  for (const p of S.getLabels()) {
    const { u, v } = frac(p.lon, p.lat);
    if (u < 0 || u > 1 || v < 0 || v > 1) continue;
    const div = document.createElement("div");
    div.className = "label3d";
    div.innerHTML = `<span class="swatch" style="background:${esc(p.color)}"></span>${esc(p.label_uz)} <span class="muted">${esc(p.area_ha)} ga</span>`;
    const obj = new CSS2DObject(div);
    const pos = local(u, v);
    pos.y += Math.max(15, S.data.size_x_m * 0.01);
    obj.position.copy(pos);
    S.labelGroup.add(obj);
  }
}

export function setLabels3d(on) {
  S.labelsOn = on;
  if (S.open) renderLabels();
}

export function setExaggeration(x) {
  S.exag = x;
  if (!S.open || !S.mesh) return;
  applyHeights();
  buildOutline();
  renderLabels();
}

// ---------------------------------------------------------------------------
// Sahna
// ---------------------------------------------------------------------------
function initScene() {
  const host = el().querySelector(".v3d-canvas");
  S.renderer = new THREE.WebGLRenderer({ antialias: true });
  S.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio));
  host.appendChild(S.renderer.domElement);
  S.labelRenderer = new CSS2DRenderer();
  S.labelRenderer.domElement.className = "v3d-labels";
  host.appendChild(S.labelRenderer.domElement);
  S.scene = new THREE.Scene();
  S.scene.background = new THREE.Color(0x0b1220);
  S.camera = new THREE.PerspectiveCamera(45, 1, 1, 1e6);
  S.controls = new OrbitControls(S.camera, S.renderer.domElement);
  S.controls.enableDamping = true;
  S.controls.maxPolarAngle = Math.PI * 0.495;
  S.scene.add(new THREE.HemisphereLight(0xffffff, 0x334155, 1.4));
  const sun = new THREE.DirectionalLight(0xffffff, 1.6);
  sun.position.set(-1, 2, -1); // shimoli-gʻarbdan (relyef soyasi bilan bir xil yoʻnalish)
  S.scene.add(sun);
  S.labelGroup = new THREE.Group();
  S.scene.add(S.labelGroup);
  S.resizeObs = new ResizeObserver(resize);
  S.resizeObs.observe(host);
  // Bosilgan nuqta → qiymatlar paneli
  const ray = new THREE.Raycaster();
  let down = null;
  S.renderer.domElement.addEventListener("pointerdown", (e) => (down = [e.clientX, e.clientY]));
  S.renderer.domElement.addEventListener("pointerup", (e) => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4 || !S.mesh) return;
    const r = S.renderer.domElement.getBoundingClientRect();
    ray.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), S.camera);
    const hit = ray.intersectObject(S.mesh)[0];
    if (!hit?.uv) return;
    const [[s, w], [n, ee]] = S.data.bounds_latlon;
    const lon = w + (ee - w) * hit.uv.x;
    const yM = my(s) + (my(n) - my(s)) * hit.uv.y;
    const lat = (2 * Math.atan(Math.exp(yM / R)) - Math.PI / 2) * (180 / Math.PI);
    const box = el().querySelector(".v3d-info");
    box.hidden = false;
    fetchPixelInto(box.querySelector(".pp"), S.runId, lon, lat);
  });
  const loop = () => {
    S.raf = requestAnimationFrame(loop);
    if (!S.open) return;
    S.controls.update();
    S.renderer.render(S.scene, S.camera);
    S.labelRenderer.render(S.scene, S.camera);
  };
  loop();
}

function resize() {
  const host = el().querySelector(".v3d-canvas");
  const w = host.clientWidth, h = host.clientHeight;
  if (!w || !h) return;
  S.renderer.setSize(w, h);
  S.labelRenderer.setSize(w, h);
  S.camera.aspect = w / h;
  S.camera.updateProjectionMatrix();
}

/** Kamerani AOI ga qaratadi (atrof rejimida ham maydon markazda boʻladi). */
export function focus3d() {
  if (!S.data || !S.camera) return;
  const ring = S.data.aoi.coordinates[0];
  const fr = ring.map(([lon, lat]) => frac(lon, lat));
  const u0 = Math.min(...fr.map((f) => f.u)), u1 = Math.max(...fr.map((f) => f.u));
  const v0 = Math.min(...fr.map((f) => f.v)), v1 = Math.max(...fr.map((f) => f.v));
  const c = local((u0 + u1) / 2, (v0 + v1) / 2);
  const span = Math.max((u1 - u0) * S.data.size_x_m, (v1 - v0) * S.data.size_y_m, 300);
  S.controls.target.copy(c);
  S.camera.position.set(c.x - span * 0.7, c.y + span * 0.9, c.z + span * 1.1);
  S.controls.update();
}

async function fetchTerrain(runId, scope) {
  if (!S.cache[scope]) S.cache[scope] = await api.terrain3d(runId, scope);
  return S.cache[scope];
}

async function buildTerrain(runId) {
  let d;
  try {
    d = await fetchTerrain(runId, S.scope);
  } catch (e) {
    if (S.scope !== "context") throw e;
    S.scope = "aoi"; // atrof relyefini olib boʻlmasa — faqat maydon
    d = await fetchTerrain(runId, "aoi");
  }
  S.data = d;
  S.heights = new Float32Array(Uint8Array.from(atob(d.heights_b64), (c) => c.charCodeAt(0)).buffer);
  if (S.mesh) {
    S.scene.remove(S.mesh);
    S.mesh.geometry.dispose();
    S.mesh.material.dispose();
    S.texture?.dispose();
  }
  const geo = new THREE.PlaneGeometry(d.size_x_m, d.size_y_m, d.width - 1, d.height - 1);
  geo.rotateX(-Math.PI / 2); // tekislik: x — sharq, z — janub, y — balandlik
  const aspect = d.size_x_m / d.size_y_m;
  const texMax = Math.min(TEX_LIMIT, S.renderer.capabilities.maxTextureSize || 2048);
  S.canvas = document.createElement("canvas");
  S.canvas.width = aspect >= 1 ? texMax : Math.round(texMax * aspect);
  S.canvas.height = aspect >= 1 ? Math.round(texMax / aspect) : texMax;
  S.ctx = S.canvas.getContext("2d");
  S.texture = new THREE.CanvasTexture(S.canvas);
  S.texture.colorSpace = THREE.SRGBColorSpace;
  S.texture.anisotropy = S.renderer.capabilities.getMaxAnisotropy();
  S.mesh = new THREE.Mesh(geo, new THREE.MeshLambertMaterial({ map: S.texture }));
  S.scene.add(S.mesh);
  applyHeights();
  buildOutline();
  S.camera.far = Math.max(d.size_x_m, d.size_y_m) * 10;
  S.camera.updateProjectionMatrix();
  focus3d();
  el().querySelector(".v3d-meta").textContent =
    `${uz.view3d.relief}: ${d.dataset} · ${d.acq_time_local} · ${Math.round(d.min_m)}–${Math.round(d.max_m)} m · ` +
    `${(d.size_x_m / 1000).toFixed(1)}×${(d.size_y_m / 1000).toFixed(1)} km · ${d.resolution_m} m`;
  document.getElementById("btn-v3d-scope")?.classList.toggle("on", S.scope === "aoi");
  // Esri tasviri fonda yuklanadi: qatlamlar darhol chiziladi, tasvir kelganda tekstura yangilanadi
  S.base = null;
  const forData = d;
  buildBase().then((base) => {
    if (S.data !== forData) return; // shu orada boshqa rejim/maydon tanlangan
    S.base = base;
    if (!base) el().querySelector(".v3d-meta").textContent += ` · ${uz.view3d.no_basemap}`;
    refresh3d();
  });
}

/** 3D rejimni ochadi. getStack — koʻrinadigan qatlamlar, getLabels — joriy sana yorliqlari. */
export async function open3d(runId, getStack, getLabels) {
  S.getStack = getStack;
  S.getLabels = getLabels;
  el().hidden = false;
  S.open = true;
  if (!S.renderer) initScene();
  resize();
  if (S.runId !== runId) {
    S.runId = runId;
    el().querySelector(".v3d-meta").textContent = uz.common.loading;
    await buildTerrain(runId);
  }
  resize();
  await paint();
  renderLabels();
}

/** «Faqat maydon» / «Atrof bilan» almashtirish. */
export async function setScope3d(scope) {
  if (scope === S.scope || !S.runId) return;
  S.scope = scope;
  el().querySelector(".v3d-meta").textContent = uz.common.loading;
  await buildTerrain(S.runId);
  await paint();
  renderLabels();
}

export function scope3d() {
  return S.scope;
}

export function close3d() {
  S.open = false;
  el().hidden = true;
  el().querySelector(".v3d-info").hidden = true;
}

/** Run almashganda yoki tozalanganda 3D maʼlumotlarni boʻshatadi. */
export function reset3d() {
  close3d();
  if (S.mesh) {
    S.scene.remove(S.mesh);
    S.mesh.geometry.dispose();
    S.mesh.material.dispose();
    S.texture?.dispose();
    S.mesh = null;
  }
  if (S.outline) S.scene?.remove(S.outline);
  S.runId = null;
  S.cache = {};
  S.scope = "context";
  S.data = null;
  S.heights = null;
  S.base = null;
}

export function is3dOpen() {
  return S.open;
}
