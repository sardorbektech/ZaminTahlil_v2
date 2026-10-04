/** Nuqtadagi barcha qiymatlar, har biri oʻz vaqti va manbasi bilan (sahifalangan; 2D popup va 3D panel uchun). */
import { api } from "../api/client.js";
import { uz } from "../i18n/uz.js";
import { esc, num } from "../ui/format.js";

function groupsHtml(data) {
  return data.groups.map((g) => {
    const rows = g.values
      .map((v) => {
        const val = v.class_label_uz ? `${esc(v.class_label_uz)}` : esc(num(v.value, 4, v.unit));
        const prev = v.prev_time_local ? ` <span class="pp-muted">(← ${esc(v.prev_time_local)})</span>` : "";
        return `<tr><td>${esc(v.label_uz)}${prev}</td><td>${val}</td></tr>`;
      })
      .join("");
    const bands = g.bands.length
      ? `<tr><td colspan="2" class="pp-muted">${esc(uz.popup.bands)}: ${g.bands.map((b) => `${esc(b.name)}=${esc(num(b.value, 4))}`).join(", ")}</td></tr>`
      : "";
    return `<div class="pp-group"><h5>${esc(g.sensor)} · ${esc(g.acq_time_local)}</h5>
      <div class="src">${esc(uz.common.source)}: ${esc(g.dataset)}${g.scene_ids.length ? ` · ${esc(g.scene_ids.slice(0, 3).join(", "))}` : ""}</div>
      <table>${rows}${bands}</table></div>`;
  });
}

/** root ichiga sahifalangan nuqta maʼlumotini chizadi (root oʻlchami belgilangan boʻlishi kerak). */
export function renderPixelInto(root, data) {
  const groups = groupsHtml(data);
  // Yer qoplami sinfi boʻlsa — sarlavhada koʻrsatiladi
  const lc = data.groups.flatMap((g) => g.values).find((v) => v.class_label_uz);
  root.innerHTML = `<div class="pp-head">${lc ? esc(lc.class_label_uz) + " · " : ""}<span class="pp-muted">${data.lat.toFixed(5)}, ${data.lon.toFixed(5)}</span></div>
    <div class="pp-body"></div>
    <div class="pp-pager"><button class="prev">‹</button><span class="pg"></span><button class="next">›</button></div>`;
  const body = root.querySelector(".pp-body");
  const pages = [];
  let cur = [];
  for (const html of groups) {
    body.insertAdjacentHTML("beforeend", html);
    if (body.scrollHeight > body.clientHeight + 1 && cur.length) {
      body.lastElementChild.remove();
      pages.push(cur);
      cur = [];
      body.innerHTML = html;
    }
    cur.push(html);
  }
  if (cur.length) pages.push(cur);
  if (!pages.length) pages.push([`<div class="pp-muted">${esc(uz.common.no_data)}</div>`]);
  let page = 0;
  const show = () => {
    body.innerHTML = pages[page].join("");
    root.querySelector(".pg").textContent = `${page + 1} / ${pages.length}`;
    root.querySelector(".prev").disabled = page === 0;
    root.querySelector(".next").disabled = page >= pages.length - 1;
  };
  root.querySelector(".prev").onclick = () => { if (page > 0) { page -= 1; show(); } };
  root.querySelector(".next").onclick = () => { if (page < pages.length - 1) { page += 1; show(); } };
  show();
}

export async function fetchPixelInto(root, runId, lon, lat) {
  root.innerHTML = `<div class="pp-body">${esc(uz.popup.loading)}</div>`;
  try {
    renderPixelInto(root, await api.pixel(runId, lon, lat));
  } catch (e) {
    root.innerHTML = `<div class="pp-body">${esc(e.status === 404 ? uz.popup.outside : e.message || uz.popup.error)}</div>`;
  }
}

export async function openPixelPopup(map, latlng, runId) {
  const root = document.createElement("div");
  root.className = "pp";
  L.popup({ maxWidth: 340, autoPanPadding: [20, 20] }).setLatLng(latlng).setContent(root).openOn(map);
  await fetchPixelInto(root, runId, latlng.lng, latlng.lat);
}
