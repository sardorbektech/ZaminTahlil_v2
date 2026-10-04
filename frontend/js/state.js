/**
 * Holat mashinasi: idle → ready → running → done | cancelled | error.
 * Ruxsat etilmagan oʻtishlar rad etiladi.
 */

export const S = {
  IDLE: "idle",
  READY: "ready",
  RUNNING: "running",
  DONE: "done",
  CANCELLED: "cancelled",
  ERROR: "error",
};

const ALLOWED = {
  idle: ["ready", "running", "done"],
  ready: ["idle", "ready", "running", "done"],
  running: ["done", "cancelled", "error"],
  done: ["idle", "ready", "running", "done"],
  cancelled: ["idle", "ready", "running", "done"],
  error: ["idle", "ready", "running", "done"],
};

class Store {
  constructor() {
    this.state = S.IDLE;
    this.aoi = null; // GeoJSON Polygon
    this.areaKm2 = 0;
    this.runId = null; // natijalari koʻrsatilayotgan run
    this.maxAoiKm2 = 100;
    this.listeners = new Set();
  }

  set(next, patch = {}) {
    if (next !== this.state && !ALLOWED[this.state].includes(next)) {
      console.warn(`Notoʻgʻri holat oʻtishi: ${this.state} → ${next}`);
      return false;
    }
    Object.assign(this, patch);
    this.state = next;
    this.listeners.forEach((fn) => fn(this));
    return true;
  }

  patch(p) {
    Object.assign(this, p);
    this.listeners.forEach((fn) => fn(this));
  }

  on(fn) {
    this.listeners.add(fn);
  }
}

export const store = new Store();
