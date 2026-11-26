import { expect, test } from "vitest";
import { fitView, GAP_X, layoutTree, NODE_H, NODE_W, zoomAt } from "./layout";
import { root, walk, type Layer } from "./map";

test("every id is unique and a layer ends when it has no children", () => {
  const seen = new Set<string>();
  walk(root, (layer) => {
    expect(seen.has(layer.id), layer.id).toBe(false);
    seen.add(layer.id);
    expect(layer.title.length).toBeGreaterThan(0);
    expect(layer.summary.length).toBeGreaterThan(0);
  });
  expect(seen.has("demo")).toBe(true);
  expect(seen.has("fwd-wg")).toBe(true);
  expect(seen.has("demo-net")).toBe(true);
});

function boxesSeparated(a: { x: number; y: number }, b: { x: number; y: number }): boolean {
  return a.x + NODE_W <= b.x || b.x + NODE_W <= a.x || a.y + NODE_H <= b.y || b.y + NODE_H <= a.y;
}

test("layout follows the parent and child edges of the schema", () => {
  const layout = layoutTree(root);
  const ids = new Set<string>();
  walk(root, (layer) => ids.add(layer.id));
  expect(layout.nodes.map((node) => node.id).sort()).toEqual([...ids].sort());

  const edges = new Set(layout.edges.map((edge) => `${edge.from}->${edge.to}`));
  let links = 0;
  walk(root, (layer, parent) => {
    if (!parent) return;
    links += 1;
    expect(edges.has(`${parent.id}->${layer.id}`)).toBe(true);
    const from = layout.nodes.find((node) => node.id === parent.id);
    const to = layout.nodes.find((node) => node.id === layer.id);
    expect(from).toBeTruthy();
    expect(to).toBeTruthy();
    expect(to!.x - from!.x).toBe(NODE_W + GAP_X);
    expect(to!.y).toBeGreaterThanOrEqual(0);
  });
  expect(layout.edges).toHaveLength(links);

  for (let i = 0; i < layout.nodes.length; i += 1) {
    for (let j = i + 1; j < layout.nodes.length; j += 1) {
      expect(boxesSeparated(layout.nodes[i], layout.nodes[j])).toBe(true);
    }
  }
  expect(layout.width).toBeGreaterThan(NODE_W);
  expect(layout.height).toBeGreaterThan(NODE_H);
});

test("empty and single-node schemas do not throw", () => {
  expect(layoutTree(null)).toEqual({ nodes: [], edges: [], width: 0, height: 0 });
  expect(layoutTree(undefined)).toEqual({ nodes: [], edges: [], width: 0, height: 0 });

  const solo: Layer = {
    id: "solo",
    title: "Solo",
    kind: "Host",
    summary: "One node.",
    facts: [],
    links: [],
    children: [],
  };
  const layout = layoutTree(solo);
  expect(layout.nodes).toHaveLength(1);
  expect(layout.edges).toHaveLength(0);
  expect(layout.nodes[0]).toMatchObject({ id: "solo", x: 0, y: 0, depth: 0 });
  expect(layout.width).toBe(NODE_W);
  expect(layout.height).toBe(NODE_H);

  const missing = layoutTree({ ...solo, id: "bare", children: undefined as unknown as Layer[] });
  expect(missing.nodes).toHaveLength(1);
  expect(missing.edges).toHaveLength(0);
});

test("fit and zoom stay finite for an empty map and a single node", () => {
  expect(fitView(0, 0, 0, 0)).toEqual({ x: 24, y: 24, scale: 1 });
  const fitted = fitView(800, 600, NODE_W, NODE_H);
  expect(fitted.scale).toBeGreaterThan(0);
  expect(Number.isFinite(fitted.x)).toBe(true);
  expect(Number.isFinite(fitted.y)).toBe(true);
  const zoomed = zoomAt(fitted, 400, 300, 1.1);
  expect(zoomed.scale).toBeGreaterThan(fitted.scale);
  expect(Number.isFinite(zoomed.x)).toBe(true);
  expect(Number.isFinite(zoomAt({ x: 0, y: 0, scale: 0 }, 10, 10, 2).scale)).toBe(true);
});
