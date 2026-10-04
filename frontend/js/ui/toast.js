/** Qisqa bildirishnomalar. */
export function toast(message, kind = "info", ms = 3500) {
  const box = document.getElementById("toasts");
  if (!box || !message) return;
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = message;
  box.appendChild(el);
  setTimeout(() => el.remove(), ms);
}
