import { expect, test } from "vitest";
import { arrowPath, diagramModel } from "./diagram";
import { root, walk, type Layer } from "./map";

test("diagram groups the same schema into sketch regions", () => {
  const model = diagramModel(root);
  const regionIds = model.regions.map((region) => region.id);
  expect(regionIds).toEqual(expect.arrayContaining(["internet", "router", "server", "docker", "system"]));

  const ids = new Set<string>();
  walk(root, (layer) => ids.add(layer.id));
  for (const node of model.nodes) expect(ids.has(node.id)).toBe(true);
  expect(model.nodes.some((node) => node.id === "hermes")).toBe(true);
  expect(model.nodes.some((node) => node.id === "caddy")).toBe(true);
  expect(model.anchors.some((anchor) => anchor.id === "docker")).toBe(true);

  const anchors = new Set(model.anchors.map((anchor) => anchor.id));
  for (const edge of model.edges) {
    expect(anchors.has(edge.from)).toBe(true);
    expect(anchors.has(edge.to)).toBe(true);
    expect(edge.from).not.toBe(edge.to);
  }
  expect(model.width).toBeGreaterThan(0);
  expect(model.height).toBeGreaterThan(0);
  expect(model.edges.length).toBeGreaterThan(0);
  expect(model.edges.length).toBeLessThanOrEqual(8);
  expect(model.relations.length).toBeGreaterThan(model.edges.length);

  const auth = model.nodes.filter((node) => node.region === "ns-auth");
  expect(auth.length).toBeGreaterThan(1);
  expect(new Set(auth.map((node) => node.x)).size).toBe(1);

  const boxes = model.nodes.map((node) => ({ x: node.x, y: node.y, w: node.w, h: node.h, id: node.id }));
  for (let i = 0; i < boxes.length; i += 1) {
    for (let j = i + 1; j < boxes.length; j += 1) {
      const a = boxes[i];
      const b = boxes[j];
      const overlaps = a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
      expect(overlaps, `${a.id} overlaps ${b.id}`).toBe(false);
    }
  }
});

test("diagram stays finite for an empty tree and a single node", () => {
  expect(diagramModel(null)).toMatchObject({ nodes: [], edges: [], width: 0, height: 0 });
  expect(diagramModel(undefined)).toMatchObject({ nodes: [], edges: [], width: 0, height: 0 });

  const solo: Layer = {
    id: "solo",
    title: "Solo",
    kind: "Host",
    summary: "One node.",
    facts: [],
    links: [],
    children: [],
  };
  const model = diagramModel(solo);
  expect(model.regions.length + model.nodes.length).toBeGreaterThan(0);
  expect(model.edges).toHaveLength(0);
  expect(Number.isFinite(model.width)).toBe(true);
  expect(Number.isFinite(model.height)).toBe(true);

  const path = arrowPath({ id: "a", x: 0, y: 0, w: 40, h: 20 }, { id: "b", x: 120, y: 0, w: 40, h: 20 });
  expect(path.startsWith("M ")).toBe(true);
});
