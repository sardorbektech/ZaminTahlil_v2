/** «Maydonlarim» oynasi: saqlangan maydonlar roʻyxati — ochish, nomini oʻzgartirish, oʻchirish (sahifalangan). */
import { api } from "../api/client.js";
import { uz } from "../i18n/uz.js";
import { esc, h, num } from "./format.js";
import { paginate } from "./paginate.js";
import { toast } from "./toast.js";

let onOpen = null;
let onDeleted = null;
let areas = [];

const modal = () => document.getElementById("areas-modal");
const host = () => document.getElementById("areas-pages");

function row(a) {
  const status = uz.areas.status[a.status] || a.status;
  return h(`<div class="area-row" data-id="${a.id}">
    <div class="area-main">
      <div class="area-name"><b>#${a.id}</b> <span class="nm">${esc(a.name)}</span></div>
      <div class="muted small">${esc(a.created_at_local)} · ${esc(num(a.area_km2, 3, uz.common.km2))} · ${esc(a.observation_dates)} ${esc(uz.areas.dates)} · ${esc(status)}</div>
    </div>
    <div class="area-actions">
      <button class="btn-primary act-open" ${a.status === "completed" ? "" : "disabled"}>${esc(uz.areas.open)}</button>
      <button class="act-rename">${esc(uz.areas.rename)}</button>
      <button class="btn-danger act-delete" ${a.status === "running" ? "disabled" : ""}>${esc(uz.areas.delete)}</button>
    </div></div>`);
}

async function reload() {
  try {
    areas = (await api.areas()).areas;
  } catch (e) {
    toast(e.message, "error");
    areas = [];
  }
  paginate(host(), areas.length ? areas.map(row) : [h(`<div class="empty">${esc(uz.areas.empty)}</div>`)], { keepPage: true });
}

export function initAreas(openCb, deletedCb) {
  onOpen = openCb;
  onDeleted = deletedCb;
  document.getElementById("btn-areas-close").onclick = () => (modal().hidden = true);
  host().addEventListener("click", async (e) => {
    const btn = e.target.closest("button");
    const rowEl = e.target.closest(".area-row");
    if (!btn || !rowEl) return;
    const id = parseInt(rowEl.dataset.id, 10);
    const area = areas.find((a) => a.id === id);
    if (btn.classList.contains("act-open")) {
      modal().hidden = true;
      onOpen?.(area);
    } else if (btn.classList.contains("act-rename")) {
      const name = prompt(uz.areas.rename_prompt, area?.name || "");
      if (name === null) return;
      try {
        await api.renameArea(id, name);
        await reload();
      } catch (err) {
        toast(err.message, "error");
      }
    } else if (btn.classList.contains("act-delete")) {
      if (!confirm(uz.areas.delete_confirm(area?.name || `#${id}`))) return;
      try {
        await api.deleteArea(id);
        toast(uz.areas.deleted);
        onDeleted?.(id);
        await reload();
      } catch (err) {
        toast(err.message, "error");
      }
    }
  });
}

export async function openAreas() {
  modal().hidden = false;
  await reload();
}
