import type { DrawingObject } from "../types";

const LAYER_ORDER: Record<string, number> = {
  background: 0,
  middle: 1,
  foreground: 2,
};

export interface CanvasRuntimeProfile {
  renderer: "svg";
  supportsSemanticEditing: boolean;
  supportsImageOverlays: boolean;
  supportsBitmapFilters: boolean;
  supportsBrushStrokes: boolean;
  supportsInfiniteCanvas: boolean;
  maxRecommendedVectorObjects: number;
}

export const SVG_CANVAS_RUNTIME: CanvasRuntimeProfile = {
  renderer: "svg",
  supportsSemanticEditing: true,
  supportsImageOverlays: true,
  supportsBitmapFilters: false,
  supportsBrushStrokes: false,
  supportsInfiniteCanvas: false,
  maxRecommendedVectorObjects: 400,
};

export function getCanvasLayerRank(layerId: string): number {
  return LAYER_ORDER[layerId] ?? LAYER_ORDER.middle;
}

export function getOrderedCanvasObjects(objects: DrawingObject[]): DrawingObject[] {
  return [...objects].sort((left, right) => {
    const layerDelta = getCanvasLayerRank(left.layer_id) - getCanvasLayerRank(right.layer_id);
    if (layerDelta !== 0) {
      return layerDelta;
    }
    if (left.z_index !== right.z_index) {
      return left.z_index - right.z_index;
    }
    return left.id.localeCompare(right.id);
  });
}
