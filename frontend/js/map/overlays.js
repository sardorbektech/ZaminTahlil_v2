/**
 * Xaritada L.imageOverlay raster qatlamlarini boshqarish moduli.
 */

let activeOverlays = {}; // { layerId: L.imageOverlay }

export function addImageLayerToMap(map, layerId, imageUrl, bounds, initialOpacity = 0.85) {
  if (activeOverlays[layerId]) {
    map.removeLayer(activeOverlays[layerId]);
  }

  const overlay = L.imageOverlay(imageUrl, bounds, {
    opacity: initialOpacity,
    interactive: true,
  });

  overlay.addTo(map);
  activeOverlays[layerId] = overlay;
  return overlay;
}

export function setLayerOpacity(layerId, opacity) {
  if (activeOverlays[layerId]) {
    activeOverlays[layerId].setOpacity(opacity);
  }
}

export function toggleLayerVisibility(map, layerId, visible) {
  const overlay = activeOverlays[layerId];
  if (!overlay) return;

  if (visible) {
    if (!map.hasLayer(overlay)) {
      overlay.addTo(map);
    }
  } else {
    if (map.hasLayer(overlay)) {
      map.removeLayer(overlay);
    }
  }
}

export function removeAllOverlays(map) {
  for (const id in activeOverlays) {
    if (map && map.hasLayer(activeOverlays[id])) {
      map.removeLayer(activeOverlays[id]);
    }
  }
  activeOverlays = {};
}
