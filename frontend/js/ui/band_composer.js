/**
 * Band kompozitsiyalari (True color, false color va maxsus R/G/B).
 */

export function getCompositeUrl(runId, type, customBands = {}) {
  let r = "B4", g = "B3", b = "B2";

  if (type === "false_color") {
    r = "B8";
    g = "B4";
    b = "B3";
  } else if (type === "custom") {
    r = customBands.r || "B4";
    g = customBands.g || "B3";
    b = customBands.b || "B2";
  }

  return `/api/v1/recon/${runId}/composite.png?r=${r}&g=${g}&b=${b}`;
}
