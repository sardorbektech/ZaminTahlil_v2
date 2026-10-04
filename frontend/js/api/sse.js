/**
 * Run hodisalari oqimi (SSE) — fetch + ReadableStream orqali, chunki kirish sarlavhasi kerak.
 * Server tarixdan boshlab yuboradi, yakuniy hodisada oqim yopiladi. Uzilsa bir necha marta qayta ulanadi.
 */
import { api } from "./client.js";

const TERMINAL = new Set(["done", "cancelled", "error", "duplicate"]);
const RETRY_MS = 1500;
const MAX_RETRIES = 5;

export function listenRun(runId, onEvent, onLost) {
  const ctrl = new AbortController();
  let lastSeq = -1;
  let finished = false;
  let retries = 0;

  const handle = (block) => {
    const data = block.split("\n").filter((l) => l.startsWith("data: ")).map((l) => l.slice(6)).join("\n");
    if (!data) return;
    let ev;
    try { ev = JSON.parse(data); } catch (_e) { return; }
    if (typeof ev.seq === "number" && ev.seq <= lastSeq) return; // qayta ulanishdagi takrorlar
    lastSeq = Math.max(lastSeq, ev.seq ?? lastSeq);
    onEvent(ev);
    if (TERMINAL.has(ev.type)) finished = true;
  };

  const run = async () => {
    while (!finished && !ctrl.signal.aborted) {
      try {
        const res = await api.stream(`/recon/${runId}/events`, ctrl.signal);
        const reader = res.body.getReader();
        const dec = new TextDecoder();
        let buf = "";
        retries = 0;
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          let i;
          while ((i = buf.indexOf("\n\n")) >= 0) {
            handle(buf.slice(0, i));
            buf = buf.slice(i + 2);
          }
          if (finished) {
            ctrl.abort();
            return;
          }
        }
      } catch (_e) {
        if (ctrl.signal.aborted) return;
      }
      if (finished) return;
      retries += 1;
      if (retries > MAX_RETRIES) {
        onLost?.();
        return;
      }
      await new Promise((r) => setTimeout(r, RETRY_MS));
    }
  };
  run();
  return { close: () => { finished = true; ctrl.abort(); } };
}
