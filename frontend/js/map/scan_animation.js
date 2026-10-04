/**
 * Skanerlash animatsiyasi (Dashed outline va moving sweep chizig'i).
 */

let sweepElement = null;

export function startScanAnimation(polygonLayer) {
  if (polygonLayer && polygonLayer._path) {
    polygonLayer._path.classList.add("scan-aoi-polygon");
  }

  const mapContainer = document.getElementById("map");
  if (mapContainer && !sweepElement) {
    sweepElement = document.createElement("div");
    sweepElement.className = "scan-sweep-line";
    mapContainer.appendChild(sweepElement);
  }
}

export function stopScanAnimation(polygonLayer) {
  if (polygonLayer && polygonLayer._path) {
    polygonLayer._path.classList.remove("scan-aoi-polygon");
  }

  if (sweepElement && sweepElement.parentNode) {
    sweepElement.parentNode.removeChild(sweepElement);
    sweepElement = null;
  }
}
