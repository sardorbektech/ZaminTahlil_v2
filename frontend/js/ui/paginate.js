/**
 * Oʻng panel (menyu) va oynalardagi uzun kontent: ichki vertikal scroll (foydalanuvchi talabi, docs/DECISIONS.md 28-qaror).
 * Sahifaning oʻzi scroll boʻlmaydi — faqat panel konteyneri ichida.
 *
 * API avvalgi sahifalovchi bilan bir xil: paginate(host, nodes, {keepPage, lastPage}).
 *   keepPage — qayta chizishda scroll holati saqlanadi; lastPage — oxiriga (masalan, chatdagi soʻnggi xabar) suriladi.
 */

const registry = new Map(); // host -> {nodes}

/**
 * host ichida nodes ni scroll qilinadigan roʻyxat sifatida koʻrsatadi.
 * @param {HTMLElement} host .paged konteyner
 * @param {Node[]} nodes elementlar
 * @param {{keepPage?: boolean, lastPage?: boolean}} opts
 */
export function paginate(host, nodes, opts = {}) {
  let body = host.querySelector(".page-body");
  if (!body) {
    host.innerHTML = '<div class="page-body scroll"></div>';
    body = host.querySelector(".page-body");
  }
  const top = body.scrollTop;
  body.replaceChildren(...nodes);
  registry.set(host, { nodes });
  if (opts.lastPage) body.scrollTop = body.scrollHeight;
  else body.scrollTop = opts.keepPage ? top : 0;
}

/** Orqaga moslik: scroll rejimida qayta oʻlchash shart emas. */
export function repaginate(_host) {}

export function repaginateAll() {}
