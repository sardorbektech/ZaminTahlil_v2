/**
 * Scroll oʻrniga sahifalash: elementlar konteyner balandligiga sigʻguncha bitta sahifaga joylanadi.
 * Sigʻmaydigan uzun jadval yoki roʻyxat qatorlar boʻyicha boʻlinadi (sarlavha takrorlanadi).
 */
import { uz } from "../i18n/uz.js";

const registry = new Map(); // host.id -> {nodes, page}

function overflows(body) {
  return body.scrollHeight > body.clientHeight + 1;
}

/** Bitta sahifaga sigʻmaydigan jadval/roʻyxatni kichik qismlarga boʻladi. */
function splitNode(node, body) {
  const tag = node.tagName;
  if (tag !== "TABLE" && tag !== "UL" && tag !== "OL" && !node.dataset?.splittable) return [node];
  const isTable = tag === "TABLE";
  const container = isTable ? node.tBodies[0] : node.dataset?.splittable ? node.querySelector("[data-rows]") || node : node;
  if (!container) return [node];
  const rows = Array.from(container.children);
  if (rows.length < 2) return [node];
  const parts = [];
  let shell = null;
  const fresh = () => {
    const c = node.cloneNode(true);
    const inner = isTable ? c.tBodies[0] : c.dataset?.splittable ? c.querySelector("[data-rows]") || c : c;
    inner.innerHTML = "";
    return [c, inner];
  };
  let [cur, inner] = fresh();
  body.replaceChildren(cur);
  for (const r of rows) {
    inner.appendChild(r.cloneNode(true));
    if (overflows(body) && inner.children.length > 1) {
      inner.removeChild(inner.lastChild);
      parts.push(cur);
      [cur, inner] = fresh();
      body.replaceChildren(cur);
      inner.appendChild(r.cloneNode(true));
    }
    shell = cur;
  }
  if (shell) parts.push(shell);
  return parts;
}

function computePages(body, nodes) {
  const pages = [];
  let cur = [];
  body.replaceChildren();
  for (const n of nodes) {
    body.appendChild(n);
    if (!overflows(body)) {
      cur.push(n);
      continue;
    }
    body.removeChild(n);
    if (cur.length) {
      pages.push(cur);
      cur = [];
    }
    body.replaceChildren(n);
    if (overflows(body)) {
      const parts = splitNode(n, body);
      parts.slice(0, -1).forEach((p) => pages.push([p]));
      const last = parts[parts.length - 1];
      body.replaceChildren(last);
      cur = [last];
    } else {
      cur = [n];
    }
  }
  if (cur.length) pages.push(cur);
  return pages.length ? pages : [[]];
}

function render(host, state) {
  const body = host.querySelector(".page-body");
  const pager = host.querySelector(".pager");
  state.pages = computePages(body, state.nodes.map((n) => n.cloneNode(true)));
  state.page = Math.min(state.page, state.pages.length - 1);
  const show = () => {
    body.replaceChildren(...state.pages[state.page]);
    pager.querySelector(".muted").textContent = `${state.page + 1} / ${state.pages.length} ${uz.common.page}`;
    pager.querySelector(".prev").disabled = state.page === 0;
    pager.querySelector(".next").disabled = state.page >= state.pages.length - 1;
    pager.style.visibility = state.pages.length > 1 ? "visible" : "hidden";
    state.onShow?.(body);
  };
  state.show = show;
  show();
}

/**
 * host ichida nodes ni sahifalab koʻrsatadi.
 * @param {HTMLElement} host .paged konteyner
 * @param {Node[]} nodes elementlar
 * @param {{keepPage?: boolean, onShow?: (body: HTMLElement) => void}} opts
 */
export function paginate(host, nodes, opts = {}) {
  if (!host.querySelector(".page-body")) {
    host.innerHTML = `<div class="page-body"></div>
      <div class="pager"><button class="prev">‹ ${uz.common.prev}</button><span class="muted"></span><button class="next">${uz.common.next} ›</button></div>`;
    host.querySelector(".prev").addEventListener("click", () => {
      const s = registry.get(host);
      if (s && s.page > 0) { s.page -= 1; s.show(); }
    });
    host.querySelector(".next").addEventListener("click", () => {
      const s = registry.get(host);
      if (s && s.page < s.pages.length - 1) { s.page += 1; s.show(); }
    });
  }
  const prev = registry.get(host);
  const state = { nodes, page: opts.keepPage && prev ? prev.page : 0, pages: [], onShow: opts.onShow };
  registry.set(host, state);
  if (host.offsetParent === null) {
    state.dirty = true; // yashirin tab: koʻrinmaguncha oʻlchab boʻlmaydi
    return;
  }
  render(host, state);
}

/** Tab ochilganda yoki oyna oʻlchami oʻzgarganda qayta sahifalash. */
export function repaginate(host) {
  const s = registry.get(host);
  if (s && host.offsetParent !== null) {
    s.dirty = false;
    render(host, s);
  }
}

export function repaginateAll() {
  registry.forEach((_s, host) => repaginate(host));
}

let resizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(repaginateAll, 150);
});
