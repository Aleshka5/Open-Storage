import { useLayoutEffect, useRef, useState } from "react";
import { fitView, layoutTree, NODE_H, NODE_W, zoomAt, type MapPoint, type MapViewBox } from "./layout";
import type { Layer } from "./map";
import "./map.css";

type Drag = {
  id: number;
  px: number;
  py: number;
  x: number;
  y: number;
  moved: boolean;
  nodeId: string | null;
};

function edgePath(from: MapPoint, to: MapPoint): string {
  const x1 = from.x + NODE_W;
  const y1 = from.y + NODE_H / 2;
  const x2 = to.x;
  const y2 = to.y + NODE_H / 2;
  const mid = (x1 + x2) / 2;
  return `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`;
}

function list(items: string[] | undefined): string[] {
  return Array.isArray(items) ? items : [];
}

function Detail({ layer, onSelect }: { layer: Layer | null; onSelect: (id: string) => void }) {
  if (!layer) {
    return <p className="os-demo-map__empty">Select a node to read its schema.</p>;
  }
  const facts = list(layer.facts);
  const links = list(layer.links);
  const children = Array.isArray(layer.children) ? layer.children : [];
  return (
    <div className="os-demo-map__detail-body">
      <p className="os-demo-map__kind">{layer.kind}</p>
      <h2 className="os-demo-map__title">{layer.title}</h2>
      <p className="os-demo-map__summary">{layer.summary}</p>
      <section className="os-demo-map__block">
        <h3 className="os-demo-map__label">Facts</h3>
        {facts.length > 0 ? (
          <ul className="os-demo-map__list">
            {facts.map((fact, index) => (
              <li className="os-demo-map__item" key={`${index}-${fact}`}>
                {fact}
              </li>
            ))}
          </ul>
        ) : (
          <p className="os-demo-map__muted">None.</p>
        )}
      </section>
      <section className="os-demo-map__block">
        <h3 className="os-demo-map__label">Links</h3>
        {links.length > 0 ? (
          <ul className="os-demo-map__list">
            {links.map((link, index) => (
              <li className="os-demo-map__item os-demo-map__item--link" key={`${index}-${link}`}>
                {link}
              </li>
            ))}
          </ul>
        ) : (
          <p className="os-demo-map__muted">None.</p>
        )}
      </section>
      <section className="os-demo-map__block">
        <h3 className="os-demo-map__label">Children</h3>
        {children.length > 0 ? (
          <ul className="os-demo-map__list">
            {children.map((child, index) => (
              <li className="os-demo-map__item" key={child?.id || index}>
                {child?.id ? (
                  <button type="button" className="os-demo-map__child" onClick={() => onSelect(child.id)}>
                    {child.title || child.id}
                  </button>
                ) : (
                  child?.title || "Untitled"
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="os-demo-map__muted">No further nodes.</p>
        )}
      </section>
    </div>
  );
}

export function MapView({ root }: { root: Layer | null | undefined }) {
  const layout = layoutTree(root);
  const layoutRef = useRef(layout);
  layoutRef.current = layout;
  const viewportRef = useRef<HTMLDivElement>(null);
  const fittedRef = useRef(false);
  const dragRef = useRef<Drag | null>(null);
  const suppressClick = useRef(false);
  const [view, setView] = useState<MapViewBox>({ x: 24, y: 24, scale: 1 });
  const [panning, setPanning] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(root?.id ?? null);

  const byId = new Map(layout.nodes.map((node) => [node.id, node]));
  const selected = (selectedId ? byId.get(selectedId)?.layer : null) ?? null;

  function fit() {
    const el = viewportRef.current;
    const box = layoutRef.current;
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
      setView(fitView(el.clientWidth, el.clientHeight, layoutRef.current.width, layoutRef.current.height));
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

  return (
    <main className="os-demo-map">
      <div className="os-demo-map__stage">
        <div className="os-demo-map__toolbar" role="toolbar" aria-label="Map">
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
          aria-label="Schema map"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
        >
          {layout.nodes.length === 0 ? (
            <p className="os-demo-map__blank">This schema has no nodes.</p>
          ) : (
            <div
              className="os-demo-map__world"
              style={{
                width: layout.width,
                height: layout.height,
                transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`,
              }}
            >
              <svg className="os-demo-map__edges" width={layout.width} height={layout.height} aria-hidden="true">
                {layout.edges.map((edge) => {
                  const from = byId.get(edge.from);
                  const to = byId.get(edge.to);
                  if (!from || !to) return null;
                  const active = edge.from === selectedId || edge.to === selectedId;
                  return (
                    <path
                      key={`${edge.from}->${edge.to}`}
                      className={active ? "os-demo-map__edge os-demo-map__edge--on" : "os-demo-map__edge"}
                      d={edgePath(from, to)}
                    />
                  );
                })}
              </svg>
              {layout.nodes.map((node, index) => (
                <button
                  key={`${node.id}-${index}`}
                  type="button"
                  data-node-id={node.id}
                  className={node.id === selectedId ? "os-demo-map__node os-demo-map__node--on" : "os-demo-map__node"}
                  style={{ left: node.x, top: node.y, width: NODE_W, height: NODE_H }}
                  aria-pressed={node.id === selectedId}
                  onClick={() => {
                    if (suppressClick.current) {
                      suppressClick.current = false;
                      return;
                    }
                    setSelectedId(node.id);
                  }}
                >
                  <span className="os-demo-map__node-kind">{node.layer.kind}</span>
                  <span className="os-demo-map__node-title">{node.layer.title}</span>
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
