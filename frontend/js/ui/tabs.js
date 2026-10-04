/** Oʻng panel tablari. Tab ochilganda uning sahifalari qayta oʻlchanadi. */
import { repaginate } from "./paginate.js";

export function initTabs() {
  const tabs = document.querySelectorAll(".tab");
  tabs.forEach((btn) =>
    btn.addEventListener("click", () => {
      tabs.forEach((b) => b.classList.toggle("active", b === btn));
      document.querySelectorAll(".tab-pane").forEach((p) => p.classList.toggle("active", p.id === `pane-${btn.dataset.tab}`));
      document.querySelectorAll(`#pane-${btn.dataset.tab} .paged`).forEach(repaginate);
    }),
  );
}
