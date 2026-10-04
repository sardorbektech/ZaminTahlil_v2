/**
 * Frontend State Machine va global holat boshqaruvi.
 * Holatlar: idle -> ready -> running -> done | cancelled | error.
 */

export const AppState = {
  IDLE: "idle",
  READY: "ready",
  RUNNING: "running",
  DONE: "done",
  CANCELLED: "cancelled",
  ERROR: "error",
};

class StateManager {
  constructor() {
    this.currentState = AppState.IDLE;
    this.currentAoi = null;
    this.currentAreaKm2 = 0.0;
    this.currentRunId = null;
    this.listeners = [];
  }

  getState() {
    return this.currentState;
  }

  setState(newState, payload = {}) {
    this.currentState = newState;
    if (payload.aoi !== undefined) this.currentAoi = payload.aoi;
    if (payload.areaKm2 !== undefined) this.currentAreaKm2 = payload.areaKm2;
    if (payload.runId !== undefined) this.currentRunId = payload.runId;

    this.notifyListeners();
  }

  subscribe(callback) {
    this.listeners.push(callback);
  }

  notifyListeners() {
    for (const cb of this.listeners) {
      cb({
        state: this.currentState,
        aoi: this.currentAoi,
        areaKm2: this.currentAreaKm2,
        runId: this.currentRunId,
      });
    }
  }
}

export const stateManager = new StateManager();
