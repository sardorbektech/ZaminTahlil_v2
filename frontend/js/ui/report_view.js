/** Hisobot va Nazorat tablari: Markdown (marked + DOMPurify) sahifalab koʻrsatiladi; hisobot .md sifatida yuklanadi. */
import { uz } from "../i18n/uz.js";
import { esc, h } from "./format.js";
import { paginate } from "./paginate.js";

let currentMd = "";
let currentName = "hisobot.md";

/** Markdown → xavfsiz HTML → yuqori darajadagi elementlar (sahifalash uchun). */
export function mdNodes(md) {
  const html = window.DOMPurify.sanitize(window.marked.parse(md || ""));
  const wrap = document.createElement("div");
  wrap.innerHTML = html;
  return Array.from(wrap.children);
}

export function renderReport(rep, runId) {
  const host = document.getElementById("report-pages");
  const meta = document.getElementById("report-meta");
  const gen = document.getElementById("btn-report-gen");
  const dl = document.getElementById("btn-report-dl");
  currentMd = "";
  if (!rep) {
    meta.textContent = "";
    gen.textContent = uz.report.generate;
    gen.disabled = runId === null;
    dl.disabled = true;
    paginate(host, [h(`<div class="empty">${esc(runId === null ? uz.common.empty_run : uz.report.not_ready)}</div>`)]);
    return;
  }
  if (rep.status === "ok") {
    currentMd = rep.content_md;
    currentName = `zamintahlil_hisobot_${rep.report_run_id}.md`;
    meta.textContent = `${uz.report.meta}: ${rep.provider} / ${rep.model} · ${rep.created_at_local}`;
    gen.textContent = uz.report.generate;
    gen.disabled = true;
    gen.title = uz.report.exists;
    dl.disabled = false;
    paginate(host, mdNodes(rep.content_md));
  } else {
    meta.textContent = `${uz.report.failed}: ${rep.error || ""}`;
    gen.textContent = uz.report.retry;
    gen.disabled = false;
    dl.disabled = true;
    paginate(host, [h(`<div class="empty">${esc(uz.report.failed)}</div>`)]);
  }
}

export function reportGenerating() {
  document.getElementById("btn-report-gen").disabled = true;
  paginate(document.getElementById("report-pages"), [h(`<div class="empty">${esc(uz.report.generating)}</div>`)]);
}

export function downloadReport() {
  if (!currentMd) return;
  const url = URL.createObjectURL(new Blob([currentMd], { type: "text/markdown;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = currentName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function renderUsage(u) {
  const host = document.getElementById("usage-pages");
  if (!u) {
    paginate(host, [h(`<div class="empty">${esc(uz.common.empty_run)}</div>`)]);
    return;
  }
  paginate(host, u.total_calls ? mdNodes(u.markdown) : [h(`<div class="empty">${esc(uz.usage.empty)}</div>`)]);
}
