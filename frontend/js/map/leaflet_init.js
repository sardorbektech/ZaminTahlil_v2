/** Leaflet xaritasi: yagona basemap (Esri World Imagery, 2D) va AOI chizish (Leaflet-Geoman). */

let map = null;
let aoiLayer = null;
let onAoi = null;
let pendingFit = null; // xarita oʻlchami 0 boʻlganda kechiktirilgan fitBounds

const AOI_STYLE = { color: "#38bdf8", weight: 2, fillColor: "#38bdf8", fillOpacity: 0.08 };

export function initMap(onAoiChanged, onMapClick) {
  onAoi = onAoiChanged;
  map = L.map("map", { center: [41.3111, 69.2797], zoom: 12, zoomControl: false, preferCanvas: false });
  L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 19,
    attribution: "Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics",
  }).addTo(map);
  L.control.zoom({ position: "bottomright" }).addTo(map);
  L.control.scale({ position: "bottomleft", imperial: false }).addTo(map);

  map.pm.setGlobalOptions({ pathOptions: AOI_STYLE, snappable: false, allowSelfIntersection: false });
  map.on("pm:create", (e) => {
    setAoiLayer(e.layer);
    e.layer.on("pm:edit", () => onAoi?.(geometry()));
  });
  map.on("click", (e) => onMapClick?.(e));
  // Konteyner oʻlchami oʻzgarsa (yoki sahifa yashirin holatda yuklangan boʻlsa) — xaritani qayta oʻlchash
  new ResizeObserver(() => {
    map.invalidateSize();
    if (pendingFit && hasRealSize()) {
      map.fitBounds(pendingFit, { padding: [30, 30] });
      pendingFit = null;
    }
  }).observe(document.getElementById("map"));
  return map;
}

/** Xarita koʻrinadigan oʻlchamga egami (yashirin sahifada 0 yoki bir necha piksel boʻlishi mumkin). */
function hasRealSize() {
  const sz = map.getSize();
  return sz.x >= 100 && sz.y >= 100;
}

function setAoiLayer(layer) {
  if (aoiLayer && aoiLayer !== layer) map.removeLayer(aoiLayer);
  aoiLayer = layer;
  onAoi?.(geometry());
}

export function geometry() {
  return aoiLayer ? aoiLayer.toGeoJSON().geometry : null;
}

export function drawShape(kind) {
  map.pm.disableDraw();
  map.pm.enableDraw(kind === "rect" ? "Rectangle" : "Polygon", { pathOptions: AOI_STYLE });
}

export function clearAoi() {
  map.pm.disableDraw();
  if (aoiLayer) map.removeLayer(aoiLayer);
  aoiLayer = null;
}

/** Saqlangan geometriyani (masalan, sahifa qayta yuklanganda) xaritaga qaytaradi. */
export function showAoi(geom, fit = true) {
  if (!geom) return;
  const layer = L.geoJSON(geom, { style: AOI_STYLE }).getLayers()[0];
  layer.addTo(map);
  if (aoiLayer && aoiLayer !== layer) map.removeLayer(aoiLayer);
  aoiLayer = layer;
  if (!fit) return;
  map.invalidateSize();
  if (hasRealSize()) map.fitBounds(layer.getBounds(), { padding: [30, 30] });
  else pendingFit = layer.getBounds();
}

export function getMap() {
  return map;
}

export function getAoiLayer() {
  return aoiLayer;
}

/** Ishlayotganda xaritaning barcha interaktivligini oʻchiradi. */
export function setMapLocked(locked) {
  const handlers = ["dragging", "touchZoom", "doubleClickZoom", "scrollWheelZoom", "boxZoom", "keyboard"];
  handlers.forEach((h) => (locked ? map[h]?.disable() : map[h]?.enable()));
  if (locked) map.pm.disableDraw();
  if (aoiLayer?.pm) locked ? aoiLayer.pm.disable() : null;
}

/** Faqat koʻrsatish uchun: sferadagi koʻpburchak maydoni (km²). Tekshiruv backendda. */
export function areaKm2(geom) {
  if (!geom) return 0;
  const R = 6378137;
  const ring = geom.coordinates[0];
  let a = 0;
  for (let i = 0; i < ring.length - 1; i++) {
    const [lon1, lat1] = ring[i].map((d) => (d * Math.PI) / 180);
    const [lon2, lat2] = ring[i + 1].map((d) => (d * Math.PI) / 180);
    a += (lon2 - lon1) * (2 + Math.sin(lat1) + Math.sin(lat2));
  }
  return Math.abs((a * R * R) / 2) / 1e6;
}
