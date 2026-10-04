/** Xarita bosilganda: nuqtadagi barcha qiymatlar, har biri oʻz vaqti va manbasi bilan (sahifalangan popup). */
import { api } from "../api/client.js";
import { uz } from "../i18n/uz.js";
import { esc, num } from "../ui/format.js";

export async function openPixelPopup(map, latlng, runId) {
  const popup = L.popup({ maxWidth: 340, autoPanPadding: [20, 20] })
    .setLatLng(latlng)
    .setContent(`<div class="pp"><div class="pp-body">${esc(uz.popup.loading)}</div></div>`)
    .openOn(map);
  let data;
  try {
    data = await api.pixel(runId, latlng.lng, latlng.lat);
  } catch (e) {
    popup.setContent(`<div class="pp"><div class="pp-body">${esc(e.status === 404 ? uz.popup.outside : e.message || uz.popup.error)}</div></div>`);
    return;
  }
  const groups = data.groups.map((g) => {
    const rows = g.values
      .map((v) => {
        const val = v.class_label_uz ? `${esc(v.class_label_uz)}` : esc(num(v.value, 4, v.unit));
        const prev = v.prev_time_local ? ` <span style="color:#64748b">(← ${esc(v.prev_time_local)})</span>` : "";
        return `<tr><td>${esc(v.label_uz)}${prev}</td><td>${val}</td></tr>`;
      })
      .join("");
    const bands = g.bands.length
      ? `<tr><td colspan="2" style="color:#475569">${esc(uz.popup.bands)}: ${g.bands.map((b) => `${esc(b.name)}=${esc(num(b.value, 4))}`).join(", ")}</td></tr>`
      : "";
    return `<div class="pp-group"><h5>${esc(g.sensor)} · ${esc(g.acq_time_local)}</h5>
      <div class="src">${esc(uz.common.source)}: ${esc(g.dataset)}${g.scene_ids.length ? ` · ${esc(g.scene_ids.slice(0, 3).join(", "))}` : ""}</div>
      <table>${rows}${bands}</table></div>`;
  });

  const root = document.createElement("div");
  root.className = "pp";
  root.innerHTML = `<div class="pp-head">${esc(uz.popup.title)} <span style="font-weight:400;color:#475569">${data.lat.toFixed(5)}, ${data.lon.toFixed(5)}</span></div>
    <div class="pp-body"></div>
    <div class="pp-pager"><button class="prev">‹</button><span class="pg"></span><button class="next">›</button></div>`;
  popup.setContent(root);

  // Sahifalarga boʻlish: popup balandligiga sigʻguncha guruhlar
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
