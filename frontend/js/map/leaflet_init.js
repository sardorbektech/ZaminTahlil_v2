/**
 * Leaflet xaritasini initsializatsiya qilish, Esri basemap va chizish vositalari.
 */

import { AppState, stateManager } from "../state.js";
import { handleMapClick } from "./pixel_popup.js";

let mapInstance = null;
let currentAoiLayer = null;

export function initMap(onAoiCreated) {
  // Toshkent koordinatalari bo'yicha markazlashtirish
  mapInstance = L.map("map", {
    center: [41.3111, 69.2797],
    zoom: 11,
    zoomControl: false,
    attributionControl: false,
  });

  // Esri World Imagery (yagona basemap, 2D)
  L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    {
      maxZoom: 19,
      attribution: "Tiles © Esri",
    }
  ).addTo(mapInstance);

  L.control.zoom({ position: "bottomright" }).addTo(mapInstance);

  // Agar Geoman kutubxonasi mavjud bo'lsa
  if (mapInstance.pm) {
    mapInstance.pm.setLang("uz");
    mapInstance.pm.setPathOptions({
      color: "#38bdf8",
      fillColor: "#38bdf8",
      fillOpacity: 0.15,
      weight: 2,
    });

    mapInstance.on("pm:create", (e) => {
      clearAoiLayer();
      currentAoiLayer = e.layer;
      const geoJson = e.layer.toGeoJSON();
      if (onAoiCreated) onAoiCreated(geoJson, currentAoiLayer);
    });
  }

  // Xaritada bosilganda piksel qiymatlarini so'rash
  mapInstance.on("click", (e) => {
    const currentState = stateManager.getState();
    if (currentState === AppState.DONE) {
      handleMapClick(mapInstance, e, stateManager.currentRunId);
    }
  });

  return mapInstance;
}

export function drawShape(shapeType) {
  if (!mapInstance || !mapInstance.pm) return;
  clearAoiLayer();
  if (shapeType === "Rectangle") {
    mapInstance.pm.enableDraw("Rectangle");
  } else if (shapeType === "Polygon") {
    mapInstance.pm.enableDraw("Polygon");
  }
}

export function clearAoiLayer() {
  if (currentAoiLayer && mapInstance) {
    mapInstance.removeLayer(currentAoiLayer);
    currentAoiLayer = null;
  }
}

export function getMapInstance() {
  return mapInstance;
}

export function getCurrentAoiLayer() {
  return currentAoiLayer;
}
