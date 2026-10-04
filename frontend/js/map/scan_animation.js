/** Run davomida AOI ustida skan animatsiyasi: harakatlanuvchi punktir chegara va AOI shakliga kesilgan nur (SVG). */

let sweep = null;
let outlined = null;
const NS = "http://www.w3.org/2000/svg";

function mercY(lat) {
  const r = (lat * Math.PI) / 180;
  return Math.log(Math.tan(Math.PI / 4 + r / 2));
}

export function startScan(map, aoiLayer) {
  stopScan(map);
  if (!aoiLayer) return;
  aoiLayer.getElement?.()?.classList.add("scan-outline");
  outlined = aoiLayer;
  const b = aoiLayer.getBounds();
  const w = b.getWest(), e = b.getEast(), n = mercY(b.getNorth()), s = mercY(b.getSouth());
  const ring = aoiLayer.toGeoJSON().geometry.coordinates[0];
  const pts = ring.map(([lon, lat]) => `${(((lon - w) / (e - w)) * 1000).toFixed(1)},${(((n - mercY(lat)) / (n - s)) * 1000).toFixed(1)}`).join(" ");

  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 1000 1000");
  svg.setAttribute("preserveAspectRatio", "none");
  svg.innerHTML = `
    <defs>
      <clipPath id="zt-aoi-clip"><polygon points="${pts}"/></clipPath>
      <linearGradient id="zt-beam" x1="0" x2="1" y1="0" y2="0">
        <stop offset="0" stop-color="#38bdf8" stop-opacity="0"/>
        <stop offset="0.8" stop-color="#38bdf8" stop-opacity="0.35"/>
        <stop offset="1" stop-color="#e0f2fe" stop-opacity="0.8"/>
      </linearGradient>
    </defs>
    <g clip-path="url(#zt-aoi-clip)">
      <rect class="beam" x="0" y="0" width="300" height="1000" fill="url(#zt-beam)"/>
    </g>`;
  sweep = L.svgOverlay(svg, b, { className: "scan-sweep", interactive: false }).addTo(map);
}

export function stopScan(map) {
  outlined?.getElement?.()?.classList.remove("scan-outline");
  outlined = null;
  if (sweep) {
    map.removeLayer(sweep);
    sweep = null;
  }
}
