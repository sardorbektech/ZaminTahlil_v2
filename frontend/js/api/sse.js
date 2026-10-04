/** Run hodisalari oqimi (SSE). Server tarixdan boshlab yuboradi, yakuniy hodisada oqim yopiladi. */

const TERMINAL = new Set(["done", "cancelled", "error", "duplicate"]);

export function listenRun(runId, onEvent, onLost) {
  const es = new EventSource(`/api/v1/recon/${runId}/events`);
  let lastSeq = -1;
  let finished = false;
  es.onmessage = (msg) => {
    let ev;
    try { ev = JSON.parse(msg.data); } catch (_e) { return; }
    if (typeof ev.seq === "number" && ev.seq <= lastSeq && ev.type === "progress") return; // qayta ulanishdagi takror
    lastSeq = Math.max(lastSeq, ev.seq ?? lastSeq);
    onEvent(ev);
    if (TERMINAL.has(ev.type)) {
      finished = true;
      es.close();
    }
  };
  es.onerror = () => {
    if (finished) return;
    // EventSource oʻzi qayta ulanadi; server yopilgan boʻlsa — xabar beramiz
    if (es.readyState === EventSource.CLOSED) onLost?.();
  };
  return { close: () => { finished = true; es.close(); } };
}
