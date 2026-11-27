import type { Layer } from "./map";

/**
 * Sketch-style view of the same Layer tree the map draws.
 * Regions are frames. Nodes and edges are layers and relationships already in the tree:
 * parent/child, plus a link whose text names another layer.
 * A frame such as systemd groups existing System layers; it is not an extra host.
 */

export type DiagramTone = "plain" | "server" | "system" | "docker";

export type DiagramBox = {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
};

export type DiagramNode = DiagramBox & {
  layer: Layer;
  region: string;
  head: boolean;
};

export type DiagramLabel = {
  id: string | null;
  text: string;
  x: number;
  y: number;
  w: number;
  h: number;
  tone: DiagramTone;
};

export type DiagramRegion = {
  id: string;
  label: string;
  layerId: string | null;
  tone: DiagramTone;
  hit: "box" | "frame";
  nest: boolean;
  x: number;
  y: number;
  w: number;
  h: number;
};

export type DiagramEdge = {
  from: string;
  to: string;
  source: "child" | "link";
};

export type DiagramModel = {
  regions: DiagramRegion[];
  nodes: DiagramNode[];
  labels: DiagramLabel[];
  anchors: DiagramBox[];
  edges: DiagramEdge[];
  relations: DiagramEdge[];
  width: number;
  height: number;
};

const NODE_W = 168;
const NODE_H = 42;
const GAP = 8;
const PAD_X = 18;
const PAD_TOP = 48;
const PAD_BOTTOM = 18;
const MARGIN = 20;
const GUTTER = 18;

const STOP = new Set([
  "network",
  "server",
  "service",
  "system",
  "public",
  "local",
  "names",
  "store",
  "common",
  "external",
  "internal",
  "storage",
  "filenkov",
]);

type BucketName = "clients" | "router" | "domain" | "internet" | "server" | "system" | "docker" | "overview";

const FRAME_BUCKET: Record<string, BucketName> = {
  clients: "clients",
  router: "router",
  "external-dns": "domain",
  internet: "internet",
  server: "server",
  docker: "docker",
};

function emptyModel(): DiagramModel {
  return { regions: [], nodes: [], labels: [], anchors: [], edges: [], relations: [], width: 0, height: 0 };
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

function linksOf(layer: Layer): string[] {
  if (!Array.isArray(layer.links)) return [];
  return layer.links.filter((item): item is string => typeof item === "string" && item.length > 0);
}

export function findLayer(root: Layer | null | undefined, id: string | null | undefined): Layer | null {
  if (!isLayer(root) || !id) return null;
  const visit = (layer: Layer): Layer | null => {
    if (layer.id === id) return layer;
    for (const child of childrenOf(layer)) {
      const found = visit(child);
      if (found) return found;
    }
    return null;
  };
  return visit(root);
}

function bucketOf(layer: Layer, ancestors: Layer[]): BucketName {
  const chain = [...ancestors, layer];
  const has = (id: string) => chain.some((item) => item.id === id);
  if (has("clients")) return "clients";
  if (has("router")) return "router";
  if (has("external-dns")) return "domain";
  if (has("caddy-public")) return "internet";
  if (has("docker")) return "docker";
  if (has("wireguard") || has("caddy") || has("dnsmasq")) return "server";
  if (chain.some((item) => item.kind === "System")) return "system";
  if (has("server")) return "server";
  if (has("internet")) return "internet";
  return "overview";
}

function blockedBefore(char: string): boolean {
  return /[a-z0-9.]/i.test(char);
}

function blockedAfter(char: string): boolean {
  return /[a-z0-9]/i.test(char);
}

export function titleMentioned(link: string, title: string): boolean {
  const hay = link.toLowerCase();
  const needle = title.trim().toLowerCase();
  if (needle.length < 3) return false;
  let from = 0;
  while (from <= hay.length - needle.length) {
    const at = hay.indexOf(needle, from);
    if (at < 0) return false;
    const before = at === 0 ? "" : hay.charAt(at - 1);
    const after = at + needle.length >= hay.length ? "" : hay.charAt(at + needle.length);
    if (!blockedBefore(before) && !blockedAfter(after)) return true;
    from = at + needle.length;
  }
  return false;
}

function titleTokens(title: string): string[] {
  return title
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((token) => token.length >= 6 && !STOP.has(token));
}

function tokenIndex(layers: Layer[]): Map<string, string> {
  const hits = new Map<string, Set<string>>();
  for (const layer of layers) {
    for (const token of titleTokens(layer.title)) {
      const set = hits.get(token) ?? new Set<string>();
      set.add(layer.id);
      hits.set(token, set);
    }
  }
  const unique = new Map<string, string>();
  for (const [token, ids] of hits) {
    if (ids.size === 1) unique.set(token, [...ids][0]);
  }
  return unique;
}

function linkMentions(link: string, layer: Layer, tokens: Map<string, string>): boolean {
  if (titleMentioned(link, layer.title)) return true;
  for (const word of link.toLowerCase().split(/[^a-z0-9]+/)) {
    if (word.length < 6) continue;
    if (tokens.get(word) === layer.id) return true;
  }
  return false;
}

export function deriveEdges(root: Layer | null | undefined): DiagramEdge[] {
  if (!isLayer(root)) return [];
  const layers: Layer[] = [];
  const parentOf = new Map<string, string | null>();
  const visit = (layer: Layer, parent: Layer | null) => {
    layers.push(layer);
    parentOf.set(layer.id, parent?.id ?? null);
    for (const child of childrenOf(layer)) visit(child, layer);
  };
  visit(root, null);

  const edges: DiagramEdge[] = [];
  const seen = new Set<string>();
  const add = (edge: DiagramEdge) => {
    const key = `${edge.source}:${edge.from}->${edge.to}`;
    if (seen.has(key) || edge.from === edge.to) return;
    seen.add(key);
    edges.push(edge);
  };

  for (const layer of layers) {
    const parent = parentOf.get(layer.id);
    if (parent) add({ from: parent, to: layer.id, source: "child" });
  }

  const tokens = tokenIndex(layers);
  for (const layer of layers) {
    for (const link of linksOf(layer)) {
      for (const other of layers) {
        if (other.id === layer.id) continue;
        if (linkMentions(link, other, tokens)) add({ from: layer.id, to: other.id, source: "link" });
      }
    }
  }
  return edges;
}

const INSET = 10;

const SPINE: Array<[string, string]> = [
  ["clients", "router"],
  ["router", "caddy"],
  ["fwd-wg", "wireguard"],
  ["external-dns", "caddy"],
  ["caddy-public", "caddy"],
  ["caddy", "ns-auth"],
];

function gridSize(count: number, cols: number): { w: number; h: number; cols: number; rows: number } {
  if (count <= 0) return { w: 0, h: 0, cols: 0, rows: 0 };
  const used = Math.min(cols, count);
  const rows = Math.ceil(count / used);
  return {
    cols: used,
    rows,
    w: used * NODE_W + (used - 1) * GAP,
    h: rows * NODE_H + (rows - 1) * GAP,
  };
}

function frameSize(innerW: number, innerH: number, minW: number, minH: number): { w: number; h: number } {
  return {
    w: Math.max(minW, innerW + PAD_X * 2),
    h: Math.max(minH, innerH + PAD_TOP + PAD_BOTTOM),
  };
}

function placeGrid(items: Layer[], originX: number, originY: number, cols: number, region: string, head: boolean): DiagramNode[] {
  const used = Math.max(1, Math.min(cols, items.length));
  return items.map((layer, index) => {
    const col = index % used;
    const row = Math.floor(index / used);
    return {
      id: layer.id,
      layer,
      region,
      head: head && index === 0,
      x: Math.round(originX + col * (NODE_W + GAP)),
      y: Math.round(originY + row * (NODE_H + GAP)),
      w: NODE_W,
      h: NODE_H,
    };
  });
}

type Stack = { id: string; items: Layer[] };

function groupBy(items: Layer[], keyOf: (layer: Layer) => string, order: string[] = []): Stack[] {
  const grouped = new Map<string, Layer[]>();
  for (const item of items) {
    const key = keyOf(item);
    const list = grouped.get(key) ?? [];
    list.push(item);
    grouped.set(key, list);
  }
  const keys = [...order.filter((key) => grouped.has(key)), ...[...grouped.keys()].filter((key) => !order.includes(key))];
  return keys.map((id) => ({ id, items: grouped.get(id) ?? [] }));
}

function climb(id: string, parentOf: Map<string, string | null>, stop: (id: string, parent: string | null) => boolean): string {
  let current = id;
  const seen = new Set<string>();
  while (!seen.has(current)) {
    seen.add(current);
    const parent = parentOf.get(current) ?? null;
    if (stop(current, parent)) return current;
    if (!parent) return current;
    current = parent;
  }
  return id;
}

function labelWidth(text: string, max: number): number {
  return Math.min(max, Math.max(96, Math.round(text.length * 9 + 32)));
}

function contentOrigin(region: Pick<DiagramRegion, "x" | "y" | "w" | "h">, grid: { w: number; h: number }, count: number) {
  const innerW = region.w - PAD_X * 2;
  const innerH = region.h - PAD_TOP - PAD_BOTTOM;
  const x = region.x + PAD_X + Math.max(0, (innerW - grid.w) / 2);
  const extraY = count > 0 && count <= 2 ? Math.max(0, (innerH - grid.h) / 2) : 0;
  return { x, y: region.y + PAD_TOP + extraY };
}

function pushLabel(labels: DiagramLabel[], anchors: DiagramBox[], region: DiagramRegion, text: string, align: "left" | "center" = "center") {
  const w = labelWidth(text, region.w - 24);
  const h = 34;
  const label: DiagramLabel = {
    id: region.layerId,
    text,
    x: Math.round(align === "left" ? region.x + 16 : region.x + (region.w - w) / 2),
    y: region.y + 8,
    w,
    h,
    tone: region.tone,
  };
  labels.push(label);
  if (label.id) anchors.push({ id: label.id, x: label.x, y: label.y, w: label.w, h: label.h });
}

export function diagramModel(root: Layer | null | undefined): DiagramModel {
  if (!isLayer(root)) return emptyModel();

  const buckets: Record<BucketName, Layer[]> = {
    clients: [],
    router: [],
    domain: [],
    internet: [],
    server: [],
    system: [],
    docker: [],
    overview: [],
  };
  const frames = new Map<BucketName, Layer>();
  const parentOf = new Map<string, string | null>();

  const visit = (layer: Layer, ancestors: Layer[]) => {
    const parent = ancestors.length > 0 ? ancestors[ancestors.length - 1] : null;
    parentOf.set(layer.id, parent?.id ?? null);
    const bucket = bucketOf(layer, ancestors);
    const frameBucket = FRAME_BUCKET[layer.id];
    if (frameBucket && frameBucket === bucket) frames.set(bucket, layer);
    else if (layer.id !== root.id || childrenOf(root).length === 0) buckets[bucket].push(layer);
    for (const child of childrenOf(layer)) visit(child, [...ancestors, layer]);
  };
  visit(root, []);

  const hostStacks = groupBy(
    buckets.server,
    (layer) => climb(layer.id, parentOf, (id) => id === "wireguard" || id === "caddy" || id === "dnsmasq"),
    ["wireguard", "caddy", "dnsmasq"],
  );
  const dockerStacks = groupBy(buckets.docker, (layer) =>
    climb(layer.id, parentOf, (_id, parent) => parent === "docker" || parent === null),
  );

  type Block = {
    id: string;
    nest: boolean;
    x: number;
    y: number;
    w: number;
    h: number;
    nodes: DiagramNode[];
  };

  const stackBlock = (stack: Stack, x: number, y: number, nest: boolean): Block => {
    const innerH = stack.items.length * NODE_H + Math.max(0, stack.items.length - 1) * GAP;
    const w = nest ? NODE_W + INSET * 2 : NODE_W;
    const h = nest ? innerH + INSET * 2 : innerH;
    return {
      id: stack.id,
      nest,
      x,
      y,
      w,
      h,
      nodes: placeGrid(stack.items, x + (nest ? INSET : 0), y + (nest ? INSET : 0), 1, stack.id, nest),
    };
  };

  const placeRow = (stacks: Stack[], y: number, gap: number): Block[] => {
    const blocks: Block[] = [];
    let x = 0;
    for (const stack of stacks) {
      const block = stackBlock(stack, x, y, stack.items.length > 1);
      blocks.push(block);
      x += block.w + gap;
    }
    return blocks;
  };

  const span = (blocks: Block[]) => ({
    w: blocks.reduce((max, block) => Math.max(max, block.x + block.w), 0),
    h: blocks.reduce((max, block) => Math.max(max, block.h), 0),
  });

  const hostBlocks = placeRow(hostStacks, 0, GUTTER);
  const hostSpan = span(hostBlocks);
  const systemGrid = gridSize(buckets.system.length, 1);
  const systemSize = buckets.system.length > 0 ? frameSize(systemGrid.w, systemGrid.h, NODE_W + 28, 110) : { w: 0, h: 0 };
  const systemLocal = { x: hostSpan.w > 0 && systemSize.w > 0 ? hostSpan.w + GUTTER : 0, y: 0, ...systemSize };
  const hostBandW = Math.max(hostSpan.w, systemLocal.x + systemSize.w);
  const hostBandH = Math.max(hostSpan.h, systemSize.h);

  const dockerBlocks = placeRow(dockerStacks, 0, 12);
  const dockerSpan = span(dockerBlocks);
  const dockerSize = dockerSpan.h > 0 ? frameSize(dockerSpan.w, dockerSpan.h, 240, 120) : { w: 0, h: 0 };
  const innerW = Math.max(hostBandW, dockerSize.w);
  const innerH = hostBandH + (dockerSize.h > 0 ? GUTTER + dockerSize.h : 0);
  const serverSize = innerH > 0 ? frameSize(innerW, innerH, 360, 220) : { w: 0, h: 0 };

  const routerGrid = gridSize(buckets.router.length, 2);
  const domainCols = buckets.domain.length > 4 ? 3 : 2;
  const domainGrid = gridSize(buckets.domain.length, domainCols);
  const internetGrid = gridSize(buckets.internet.length, 1);
  const routerSize = buckets.router.length > 0 ? frameSize(routerGrid.w, routerGrid.h, 240, 120) : { w: 0, h: 0 };
  const domainSize = buckets.domain.length > 0 ? frameSize(domainGrid.w, domainGrid.h, 280, 140) : { w: 0, h: 0 };
  const clientsSize = frames.get("clients") ? { w: 200, h: 78 } : { w: 0, h: 0 };
  const internetSize = buckets.internet.length > 0 ? frameSize(internetGrid.w, internetGrid.h, 210, 130) : { w: 0, h: 0 };
  const overviewGrid = gridSize(buckets.overview.length, 2);
  const overviewSize =
    buckets.overview.length === 0
      ? { w: 0, h: 0 }
      : buckets.overview.length === 1
        ? { w: 220, h: 78 }
        : frameSize(overviewGrid.w, overviewGrid.h, 240, 110);

  const topH = Math.max(clientsSize.h, routerSize.h, domainSize.h);
  const lane = topH > 0 && serverSize.h > 0 ? 40 : GUTTER;
  const bodyY = MARGIN + (topH > 0 ? topH + lane : 0);
  const showInternet = internetSize.w > 0;
  const serverX = MARGIN + (showInternet ? internetSize.w + GUTTER : 0);
  const serverRect = { x: serverX, y: bodyY, ...serverSize };
  const internetRect = { x: MARGIN, y: bodyY, ...internetSize };
  const clientsRect = { x: serverRect.w > 0 ? serverRect.x : MARGIN, y: MARGIN, ...clientsSize };
  const routerRect = {
    x: (clientsSize.w > 0 ? clientsRect.x + clientsRect.w + GUTTER : clientsRect.x),
    y: MARGIN,
    ...routerSize,
  };
  const domainRect = {
    x: routerSize.w > 0 ? routerRect.x + routerRect.w + GUTTER : routerRect.x,
    y: MARGIN,
    ...domainSize,
  };
  const overviewRect = { x: MARGIN, y: MARGIN, ...overviewSize };

  const regions: DiagramRegion[] = [];
  const addRegion = (
    id: string,
    label: string,
    layerId: string | null,
    tone: DiagramTone,
    hit: "box" | "frame",
    nest: boolean,
    rect: { x: number; y: number; w: number; h: number },
  ) => {
    if (rect.w <= 0 || rect.h <= 0) return;
    regions.push({
      id,
      label,
      layerId,
      tone,
      hit,
      nest,
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      w: Math.round(rect.w),
      h: Math.round(rect.h),
    });
  };

  if (serverSize.h > 0) {
    addRegion("server", frames.get("server")?.title ?? "Server", frames.get("server")?.id ?? null, "server", "frame", false, serverRect);
  }
  const content = {
    x: serverRect.x + PAD_X,
    y: serverRect.y + PAD_TOP,
  };
  if (systemSize.h > 0) {
    addRegion("system", "systemd", null, "system", "frame", false, {
      x: content.x + systemLocal.x,
      y: content.y + systemLocal.y,
      ...systemSize,
    });
  }
  if (dockerSize.h > 0) {
    addRegion("docker", frames.get("docker")?.title ?? "Docker", frames.get("docker")?.id ?? null, "docker", "frame", false, {
      x: content.x,
      y: content.y + hostBandH + GUTTER,
      ...dockerSize,
    });
  }
  for (const block of hostBlocks) {
    if (!block.nest) continue;
    addRegion(`group-${block.id}`, "", null, "plain", "frame", true, {
      x: content.x + block.x,
      y: content.y + block.y,
      w: block.w,
      h: block.h,
    });
  }
  const dockerRegion = regions.find((region) => region.id === "docker");
  for (const block of dockerBlocks) {
    if (!block.nest || !dockerRegion) continue;
    addRegion(`group-${block.id}`, "", null, "plain", "frame", true, {
      x: dockerRegion.x + PAD_X + block.x,
      y: dockerRegion.y + PAD_TOP + block.y,
      w: block.w,
      h: block.h,
    });
  }
  if (clientsSize.w > 0 && frames.get("clients")) {
    addRegion("clients", frames.get("clients")!.title, frames.get("clients")!.id, "plain", "box", false, clientsRect);
  }
  if (routerSize.h > 0) {
    addRegion("router", frames.get("router")?.title ?? "Router", frames.get("router")?.id ?? null, "plain", "frame", false, routerRect);
  }
  if (domainSize.h > 0) {
    addRegion("domain", frames.get("domain")?.title ?? "External DNS", frames.get("domain")?.id ?? null, "plain", "frame", false, domainRect);
  }
  if (showInternet) {
    addRegion("internet", frames.get("internet")?.title ?? "Internet", frames.get("internet")?.id ?? null, "plain", "frame", false, internetRect);
  }
  if (overviewSize.h > 0) {
    const solo = buckets.overview.length === 1 ? buckets.overview[0] : null;
    addRegion("overview", solo?.title ?? root.title, solo?.id ?? null, "plain", solo ? "box" : "frame", false, overviewRect);
  }

  const regionById = new Map(regions.map((region) => [region.id, region]));
  const nodes: DiagramNode[] = [];
  const shift = (block: Block, dx: number, dy: number) => {
    for (const node of block.nodes) {
      nodes.push({ ...node, x: Math.round(node.x + dx), y: Math.round(node.y + dy) });
    }
  };
  for (const block of hostBlocks) shift(block, content.x, content.y);
  if (dockerRegion) {
    for (const block of dockerBlocks) shift(block, dockerRegion.x + PAD_X, dockerRegion.y + PAD_TOP);
  }

  const placeInto = (name: string, cols: number, head: boolean) => {
    const region = regionById.get(name);
    const items = buckets[name as BucketName] ?? [];
    if (!region || items.length === 0) return;
    const grid = gridSize(items.length, cols);
    const at = contentOrigin(region, grid, items.length);
    nodes.push(...placeGrid(items, at.x, at.y, cols, name, head));
  };
  placeInto("router", 2, false);
  placeInto("domain", domainCols, false);
  placeInto("internet", 1, false);
  placeInto("system", 1, false);
  if (!(buckets.overview.length === 1 && regionById.get("overview")?.hit === "box")) placeInto("overview", 2, false);

  const labels: DiagramLabel[] = [];
  const anchors: DiagramBox[] = nodes.map((node) => ({ id: node.id, x: node.x, y: node.y, w: node.w, h: node.h }));
  for (const region of regions) {
    if (!region.label) continue;
    if (region.hit === "box" && region.layerId) anchors.push({ id: region.layerId, x: region.x, y: region.y, w: region.w, h: region.h });
    else pushLabel(labels, anchors, region, region.label, region.id === "server" ? "left" : "center");
  }
  for (const region of regions) {
    if (region.hit === "frame" && region.layerId) {
      anchors.push({ id: region.layerId, x: region.x, y: region.y, w: region.w, h: region.h });
    }
  }

  const anchorById = new Map<string, DiagramBox>();
  for (const anchor of anchors) anchorById.set(anchor.id, anchor);

  const boxOf = (id: string): DiagramBox | null => anchorById.get(id) ?? null;
  const edges: DiagramEdge[] = [];
  const seen = new Set<string>();
  for (const [from, to] of SPINE) {
    if (!boxOf(from) || !boxOf(to) || from === to) continue;
    const key = `${from}->${to}`;
    if (seen.has(key)) continue;
    seen.add(key);
    edges.push({ from, to, source: "child" });
  }

  const relations: DiagramEdge[] = [];
  for (const edge of deriveEdges(root)) {
    if (edge.source !== "link") continue;
    if (!boxOf(edge.from) || !boxOf(edge.to)) continue;
    const key = `${edge.from}->${edge.to}`;
    if (seen.has(key)) continue;
    seen.add(key);
    relations.push(edge);
  }

  let width = 0;
  let height = 0;
  const extend = (x: number, y: number, w: number, h: number) => {
    width = Math.max(width, x + w);
    height = Math.max(height, y + h);
  };
  for (const region of regions) extend(region.x, region.y, region.w, region.h);
  for (const node of nodes) extend(node.x, node.y, node.w, node.h);
  if (width > 0) width += MARGIN;
  if (height > 0) height += MARGIN;

  return { regions, nodes, labels, anchors, edges, relations, width, height };
}

export function arrowPath(from: DiagramBox, to: DiagramBox): string {
  const fromCx = from.x + from.w / 2;
  const fromCy = from.y + from.h / 2;
  const toCx = to.x + to.w / 2;
  const toCy = to.y + to.h / 2;
  const dx = toCx - fromCx;
  const dy = toCy - fromCy;
  const round = (value: number) => Math.round(value * 10) / 10;
  const lane = ((from.id.length * 3 + to.id.length * 5) % 5 - 2) * 10;

  if (Math.abs(dy) >= Math.abs(dx)) {
    const y1 = dy >= 0 ? from.y + from.h : from.y;
    const y2 = dy >= 0 ? to.y : to.y + to.h;
    const mid = (y1 + y2) / 2 + lane;
    return `M ${round(fromCx)} ${round(y1)} L ${round(fromCx)} ${round(mid)} L ${round(toCx)} ${round(mid)} L ${round(toCx)} ${round(y2)}`;
  }

  const x1 = dx >= 0 ? from.x + from.w : from.x;
  const x2 = dx >= 0 ? to.x : to.x + to.w;
  const mid = (x1 + x2) / 2 + lane;
  return `M ${round(x1)} ${round(fromCy)} L ${round(mid)} ${round(fromCy)} L ${round(mid)} ${round(toCy)} L ${round(x2)} ${round(toCy)}`;
}
