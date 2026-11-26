import type { Layer } from "./map";

export const NODE_W = 196;
export const NODE_H = 68;
export const GAP_X = 72;
export const GAP_Y = 22;

export type MapPoint = {
  id: string;
  layer: Layer;
  x: number;
  y: number;
  depth: number;
};

export type MapEdge = {
  from: string;
  to: string;
};

export type MapLayout = {
  nodes: MapPoint[];
  edges: MapEdge[];
  width: number;
  height: number;
};

export type MapViewBox = {
  x: number;
  y: number;
  scale: number;
};

const MIN_SCALE = 0.08;
const MAX_SCALE = 2.5;

function emptyLayout(): MapLayout {
  return { nodes: [], edges: [], width: 0, height: 0 };
}

function isLayer(value: unknown): value is Layer {
  if (!value || typeof value !== "object") return false;
  const layer = value as Partial<Layer>;
  return typeof layer.id === "string" && layer.id.length > 0;
}

function childrenOf(layer: Layer): Layer[] {
  if (!Array.isArray(layer.children)) return [];
  return layer.children.filter(isLayer);
}

export function layoutTree(root: Layer | null | undefined): MapLayout {
  if (!isLayer(root)) return emptyLayout();

  const nodes: MapPoint[] = [];
  const edges: MapEdge[] = [];
  let slot = 0;
  const pitchY = NODE_H + GAP_Y;
  const pitchX = NODE_W + GAP_X;

  const place = (layer: Layer, depth: number): number => {
    const children = childrenOf(layer);
    if (children.length === 0) {
      const y = slot * pitchY;
      slot += 1;
      nodes.push({ id: layer.id, layer, x: depth * pitchX, y, depth });
      return y;
    }
    const childY: number[] = [];
    for (const child of children) {
      edges.push({ from: layer.id, to: child.id });
      childY.push(place(child, depth + 1));
    }
    const y = (childY[0] + childY[childY.length - 1]) / 2;
    nodes.push({ id: layer.id, layer, x: depth * pitchX, y, depth });
    return y;
  };

  place(root, 0);

  let width = 0;
  let height = 0;
  for (const node of nodes) {
    width = Math.max(width, node.x + NODE_W);
    height = Math.max(height, node.y + NODE_H);
  }
  return { nodes, edges, width, height };
}

export function clampScale(scale: number): number {
  if (!Number.isFinite(scale)) return 1;
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));
}

export function zoomAt(view: MapViewBox, originX: number, originY: number, factor: number): MapViewBox {
  const current = view.scale === 0 || !Number.isFinite(view.scale) ? 1 : view.scale;
  const scale = clampScale(current * factor);
  const ratio = scale / current;
  return {
    scale,
    x: originX - (originX - view.x) * ratio,
    y: originY - (originY - view.y) * ratio,
  };
}

export function fitView(viewportWidth: number, viewportHeight: number, layoutWidth: number, layoutHeight: number): MapViewBox {
  if (viewportWidth <= 0 || viewportHeight <= 0 || layoutWidth <= 0 || layoutHeight <= 0) {
    return { x: 24, y: 24, scale: 1 };
  }
  const pad = 36;
  const availableW = Math.max(viewportWidth - pad * 2, 1);
  const availableH = Math.max(viewportHeight - pad * 2, 1);
  const scale = Math.min(MAX_SCALE, Math.max(0.05, Math.min(availableW / layoutWidth, availableH / layoutHeight, 1.25)));
  return {
    scale,
    x: (viewportWidth - layoutWidth * scale) / 2,
    y: (viewportHeight - layoutHeight * scale) / 2,
  };
}
