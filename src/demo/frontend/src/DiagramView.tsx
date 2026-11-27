import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { arrowPath, diagramModel, findLayer } from "./diagram";
import { fitView, zoomAt, type MapViewBox } from "./layout";
import type { Layer } from "./map";
import { Detail } from "./MapView";
import "./diagram.css";

type Drag = {
  id: number;
  px: number;
  py: number;
  x: number;
  y: number;
  moved: boolean;
  nodeId: string | null;
};

export function DiagramView({ root }: { root: Layer | null | undefined }) {
  const model = useMemo(() => diagramModel(root), [root]);
  const modelRef = useRef(model);
  modelRef.current = model;
  const viewportRef = useRef<HTMLDivElement>(null);
  const fittedRef = useRef(false);
  const dragRef = useRef<Drag | null>(null);
  const suppressClick = useRef(false);
  const [view, setView] = useState<MapViewBox>({ x: 24, y: 24, scale: 1 });
  const [panning, setPanning] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(root?.id ?? null);

  const anchorById = new Map(model.anchors.map((anchor) => [anchor.id, anchor]));
  const selected = findLayer(root, selectedId);

  function fit() {
    const el = viewportRef.current;
    const box = modelRef.current;
    if (!el) return;
    setView(fitView(el.clientWidth, el.clientHeight, box.width, box.height));
  }

  useLayoutEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    const tryFit = () => {
      if (fittedRef.current) return;
      if (el.clientWidth === 0 || el.clientHeight === 0) return;
      fittedRef.current = true;
      setView(fitView(el.clientWidth, el.clientHeight, modelRef.current.width, modelRef.current.height));
    };
    tryFit();
    const observer = new ResizeObserver(tryFit);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useLayoutEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      if (event.deltaY === 0) return;
      const rect = el.getBoundingClientRect();
      const factor = event.deltaY > 0 ? 1 / 1.1 : 1.1;
      setView((current) => zoomAt(current, event.clientX - rect.left, event.clientY - rect.top, factor));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  function zoomBy(factor: number) {
    const el = viewportRef.current;
    if (!el) return;
    setView((current) => zoomAt(current, el.clientWidth / 2, el.clientHeight / 2, factor));
  }

  function reset() {
    setView({ x: 24, y: 24, scale: 1 });
  }

  function onPointerDown(event: React.PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    const target = event.target;
    const node = target instanceof Element ? target.closest("[data-node-id]") : null;
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // A pointer that is already gone still pans from the events we do receive.
    }
    dragRef.current = {
      id: event.pointerId,
      px: event.clientX,
      py: event.clientY,
      x: view.x,
      y: view.y,
      moved: false,
      nodeId: node?.getAttribute("data-node-id") ?? null,
    };
  }

  function onPointerMove(event: React.PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag || drag.id !== event.pointerId) return;
    const dx = event.clientX - drag.px;
    const dy = event.clientY - drag.py;
    if (!drag.moved) {
      if (Math.hypot(dx, dy) < 4) return;
      drag.moved = true;
      setPanning(true);
    }
    setView((current) => ({ ...current, x: drag.x + dx, y: drag.y + dy }));
  }

  function endDrag(event: React.PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag || drag.id !== event.pointerId) return;
    dragRef.current = null;
    setPanning(false);
    if (drag.moved) {
      suppressClick.current = true;
      requestAnimationFrame(() => {
        suppressClick.current = false;
      });
      return;
    }
    if (drag.nodeId) setSelectedId(drag.nodeId);
  }

  const empty = model.nodes.length === 0 && model.regions.length === 0;

  return (
    <main className="os-demo-map os-demo-diagram">
      <div className="os-demo-map__stage">
        <div className="os-demo-map__toolbar" role="toolbar" aria-label="Diagram">
          <button type="button" className="os-demo-map__tool" onClick={() => zoomBy(1 / 1.2)}>
            Zoom out
          </button>
          <button type="button" className="os-demo-map__tool" onClick={() => zoomBy(1.2)}>
            Zoom in
          </button>
          <button type="button" className="os-demo-map__tool" onClick={fit}>
            Fit
          </button>
          <button type="button" className="os-demo-map__tool" onClick={reset}>
            Reset
          </button>
          <span className="os-demo-map__scale">{Math.round(view.scale * 100)}%</span>
        </div>
        <div
          ref={viewportRef}
          className={panning ? "os-demo-map__viewport os-demo-map__viewport--panning" : "os-demo-map__viewport"}
          aria-label="Schema diagram"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
        >
          {empty ? (
            <p className="os-demo-map__blank">This schema has no nodes.</p>
          ) : (
            <div
              className="os-demo-diagram__world"
              style={{
                width: model.width,
                height: model.height,
                transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`,
              }}
            >
              {model.regions.map((region) =>
                region.hit === "box" ? (
                  <button
                    key={region.id}
                    type="button"
                    data-node-id={region.layerId ?? undefined}
                    className={
                      region.layerId === selectedId
                        ? "os-demo-diagram__region os-demo-diagram__region--box os-demo-diagram__region--on"
                        : "os-demo-diagram__region os-demo-diagram__region--box"
                    }
                    style={{ left: region.x, top: region.y, width: region.w, height: region.h }}
                    aria-pressed={region.layerId === selectedId}
                    onClick={() => {
                      if (suppressClick.current || !region.layerId) return;
                      setSelectedId(region.layerId);
                    }}
                  >
                    {region.label}
                  </button>
                ) : (
                  <div
                    key={region.id}
                    className={`os-demo-diagram__region os-demo-diagram__region--${region.tone}${region.nest ? " os-demo-diagram__region--group" : ""}`}
                    style={{ left: region.x, top: region.y, width: region.w, height: region.h }}
                  />
                ),
              )}
              <svg className="os-demo-diagram__edges" width={model.width} height={model.height} aria-hidden="true">
                <defs>
                  <marker id="os-demo-diagram-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">
                    <path fill="context-stroke" d="M0 0 L8 4 L0 8 Z" />
                  </marker>
                </defs>
                {[
                  ...model.edges.map((edge) => ({ ...edge, relation: false })),
                  ...model.relations
                    .filter((edge) => edge.from === selectedId || edge.to === selectedId)
                    .map((edge) => ({ ...edge, relation: true })),
                ].map((edge) => {
                  const from = anchorById.get(edge.from);
                  const to = anchorById.get(edge.to);
                  if (!from || !to) return null;
                  const active = edge.relation || edge.from === selectedId || edge.to === selectedId;
                  const className = [
                    "os-demo-diagram__edge",
                    active ? "os-demo-diagram__edge--on" : "",
                    edge.relation ? "os-demo-diagram__edge--relation" : "",
                  ]
                    .filter(Boolean)
                    .join(" ");
                  return (
                    <path
                      key={`${edge.relation ? "rel" : "flow"}:${edge.from}->${edge.to}`}
                      className={className}
                      d={arrowPath(from, to)}
                      markerEnd="url(#os-demo-diagram-arrow)"
                    />
                  );
                })}
              </svg>
              {model.labels.map((label) =>
                label.id ? (
                  <button
                    key={`${label.id}-${label.x}`}
                    type="button"
                    data-node-id={label.id}
                    className={
                      label.id === selectedId
                        ? "os-demo-diagram__label os-demo-diagram__label--on"
                        : "os-demo-diagram__label"
                    }
                    style={{ left: label.x, top: label.y, width: label.w, height: label.h }}
                    aria-pressed={label.id === selectedId}
                    onClick={() => {
                      if (suppressClick.current) return;
                      setSelectedId(label.id);
                    }}
                  >
                    {label.text}
                  </button>
                ) : (
                  <div
                    key={`${label.text}-${label.x}`}
                    className="os-demo-diagram__label os-demo-diagram__label--static"
                    style={{ left: label.x, top: label.y, width: label.w, height: label.h }}
                  >
                    {label.text}
                  </div>
                ),
              )}
              {model.nodes.map((node) => (
                <button
                  key={node.id}
                  type="button"
                  data-node-id={node.id}
                  className={[
                    "os-demo-diagram__node",
                    node.head ? "os-demo-diagram__node--head" : "",
                    node.id === selectedId ? "os-demo-diagram__node--on" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  style={{ left: node.x, top: node.y, width: node.w, height: node.h }}
                  aria-pressed={node.id === selectedId}
                  onClick={() => {
                    if (suppressClick.current) return;
                    setSelectedId(node.id);
                  }}
                >
                  {node.layer.title}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
      <aside className="os-demo-map__detail" aria-label="Schema detail">
        <Detail layer={selected} onSelect={setSelectedId} />
      </aside>
    </main>
  );
}
