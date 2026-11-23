/**
 * Geometry and spring for the liquid-glass theme blob (ADR-0004 items 4 and 6,
 * US-10 task-03).
 *
 * The blob is one element inside the popover's glass host. Away from the rows
 * it is a circle; over a row it is a pill ("well") that leans toward the
 * pointer. The paint lives in ThemeControl.css; this module owns only what the
 * pointer loop writes: left, top, width, height and borderRadius.
 *
 * Coordinates are the host's own: the caller subtracts `hostRect.left` and
 * `hostRect.top` from client coordinates, and the results are written straight
 * to `style.left` / `style.top`. The geometry functions below do not read the
 * DOM and do not start a frame.
 */

import { mountGlassLens, type GlassLens } from "./glassLens";

/**
 * Geometry rules
 * --------------
 * - With no active row the blob is a circle: `r = max(rowH/2 - WELL_INSET, 14)`
 *   sits centred on the row (`cy`) and horizontally on the pointer (`px`),
 *   clamped inside the host. The row tells it what size the well becomes, so a
 *   pointer that leaves the rows keeps the height it had.
 * - Over row `i` the blob is the well: `h = rows[i].height`, `wellH =
 *   h - 2 * WELL_INSET` tall and `wellR = wellH / 2` round. Its width is
 *   `11 * wellH` (a capsule the pointer cannot outrun), its centre is
 *   `px + a * 2.5 * wellH` with `a = sign(px - rowCentreX)`, so the bulge leads
 *   the pointer, and it is clamped inside the host with `tokens.rowInset` of
 *   air. A pointer over the middle stays centred; a pointer at an edge leans
 *   that way.
 * - The row's vertical middle wins over the pointer's y: a well does not shrink
 *   when the pointer is near its edge.
 * - Clamp, always last: no input can put the blob outside the host.
 */

/** Blob rest, circle form. */
export const CIRCLE_RADIUS = 14;
/** Fallback well height when the rows cannot be measured. */
const WELL_FALLBACK = 48;
/** Air between a well and its row, top and bottom. */
export const WELL_INSET = 4;
/** Spring stiffness, applied each frame to the position error. */
export const STIFFNESS = 0.18;
/** Per-frame velocity decay. */
export const DAMPING = 0.78;
/** Largest distance a single frame may advance any axis. */
export const MAX_STEP = 34;
/** The loop stops once every axis is this close and this slow. */
export const SETTLE_EPSILON = 0.5;

/** A written frame, in host coordinates. */
export type Frame = Readonly<{ left: number; top: number; width: number; height: number; radius: number }>;

/** A box in host coordinates; DOMRect, getBoundingClientRect and literals fit. */
export type Box = Readonly<{ left: number; top: number; width: number; height: number }>;

export type Point = Readonly<{ x: number; y: number }>;

/** A row: its top-left corner and height in host coordinates. */
export type RowBox = Readonly<{ x: number; y: number; height: number }>;

export type RowSet = Readonly<{ rows: ReadonlyArray<RowBox>; active: number }>;

export type Tokens = Readonly<{ radius: number; rowInset: number; stretch: number }>;

export type BlobCircle = Readonly<{ circle: true; cx: number; cy: number; r: number }>;

export type BlobPill = Readonly<{
  circle: false;
  left: number;
  top: number;
  width: number;
  height: number;
  radius: number;
}>;

export type BlobGeometry = BlobCircle | BlobPill;

export const DEFAULT_TOKENS: Tokens = { radius: CIRCLE_RADIUS, rowInset: 6, stretch: 1.6 };

function clamp(value: number, min: number, max: number): number {
  if (max < min) return (min + max) / 2;
  return value < min ? min : value > max ? max : value;
}

function finite(value: number, fallback: number): number {
  return Number.isFinite(value) ? value : fallback;
}

/**
 * The shape the blob should have this frame. Pure: same input, same output.
 *
 * `tokens.rowInset` is the air kept between the blob and the host edge,
 * `tokens.stretch` multiplies the pointer's distance from the row centre, and
 * `tokens.radius` overrides the circle radius.
 */
export function blobGeometry(
  host: Box,
  set: RowSet | null,
  pointer: Point | null,
  tokens: Tokens,
): BlobGeometry {
  const inset = Math.max(0, finite(tokens.rowInset, DEFAULT_TOKENS.rowInset));
  const stretch = Math.max(0, finite(tokens.stretch, DEFAULT_TOKENS.stretch));
  const rawRadius = finite(tokens.radius, 0);
  const hostW = Math.max(0, finite(host.width, 0));
  const hostH = Math.max(0, finite(host.height, 0));
  const hostLeft = finite(host.left, 0);
  const hostTop = finite(host.top, 0);

  const list = set ? set.rows : [];
  // The pointer decides the row when it is over one: a global move reports no
  // per-element enter, so the row is read from the coordinate, not from an event.
  const hovered =
    pointer && Number.isFinite(pointer.x) && Number.isFinite(pointer.y)
      ? list.findIndex((box) => pointer.y >= box.y && pointer.y <= box.y + box.height)
      : -1;
  const active = hovered >= 0 ? hovered : set ? set.active : -1;
  const row = active >= 0 && active < list.length ? list[active] : null;
  // A pointer that has left the rows still knows what a well looks like.
  const reference = row ?? list[active] ?? list[0] ?? null;
  const rowH = Math.max(0, finite(reference?.height ?? 0, 0));
  const wellH = Math.max(0, rowH - 2 * WELL_INSET);
  const wellR = Math.min((wellH || WELL_FALLBACK) / 2, Math.max(0, hostH / 2 - inset));
  const px = pointer && Number.isFinite(pointer.x) ? pointer.x : null;

  if (!row) {
    // Circle: the well's height, sitting under the cursor.
    // `tokens.radius` exists for tests and callers that want a fixed dot.
    const r = rawRadius > 0 ? rawRadius : Math.max(0, wellR);
    const cx = px === null ? hostLeft + hostW / 2 : px;
    const cy = reference ? finite(reference.y, 0) + rowH / 2 : hostTop + hostH / 2;
    return {
      circle: true,
      cx: clamp(cx, hostLeft + inset + r, hostLeft + hostW - inset - r),
      cy: clamp(cy, hostTop + inset + r, hostTop + hostH - inset - r),
      r,
    };
  }

  // Well: a wide capsule, leaning toward the pointer and clamped inside the host.
  const rowCx = finite(row.x, 0) + hostW / 2;
  const lean = px === null ? 0 : Math.sign(px - rowCx) * Math.min(Math.abs(px - rowCx), 2.5 * wellH) * stretch;
  const room = Math.max(0, hostW - 2 * inset);
  // A well nearly fills its row: a click has somewhere to land that is not the rim.
  const width = Math.max(0, Math.min(room, Math.max(9 * wellH, Math.min(11 * wellH, room * 0.86))));
  const cx = clamp(px === null ? rowCx : px + lean, hostLeft + inset + width / 2, hostLeft + hostW - inset - width / 2);
  const top = clamp(
    finite(row.y, 0) + rowH / 2 - wellH / 2,
    hostTop + inset,
    hostTop + hostH - inset - wellH,
  );
  return {
    circle: false,
    left: cx - width / 2,
    top,
    width,
    height: wellH,
    radius: wellH / 2,
  };
}

/** The frame a geometry settles at: a circle becomes its bounding square. */
export function geometryToFrame(geometry: BlobGeometry): Frame {
  if (geometry.circle) {
    const { cx, cy, r } = geometry;
    return { left: cx - r, top: cy - r, width: r * 2, height: r * 2, radius: r };
  }
  const { left, top, width, height, radius } = geometry;
  return { left, top, width, height, radius };
}

const AXES = ["left", "top", "width", "height", "radius"] as const;

export type Spring = {
  /** Advance one frame toward `target`. */
  step(target: Frame): Frame;
  /** The frame the spring last produced. */
  current(): Frame;
  /** Place immediately, with no velocity. */
  place(frame: Frame): void;
  /** True when every axis is within `SETTLE_EPSILON` and its velocity under it. */
  settled(target: Frame): boolean;
};

/**
 * A critically-damped-ish spring per axis, as ADR-0004 fixes it:
 * `v = (v + (target - pos) * 0.18) * 0.78`, `pos += v`, and the per-frame
 * advance is capped at 34px.
 *
 * The cap holds `|pos - target|` to at most its previous value for that axis,
 * so a step either closes the gap or leaves it the same and a position can
 * never cross to the far side of the target. An axis that would pass its target
 * lands on it and stops. The approach from any offset start is therefore
 * monotone: there is no overshoot.
 *
 * Width, height and radius ride the same spring, so a circle-to-pill morph
 * glides instead of jumping.
 *
 * Consequence worth knowing: a target that keeps moving faster than `|v|` can
 * grow will leave `settled()` false, and the loop keeps running until the
 * pointer stops. That is intended, because the caller passes the settled
 * target only when the pointer is at rest.
 */
export function createSpring(initial: Frame): Spring {
  const pos = new Map<string, number>();
  const vel = new Map<string, number>();
  for (const axis of AXES) {
    pos.set(axis, finite(initial[axis], 0));
    vel.set(axis, 0);
  }

  const read = (): Frame => ({
    left: pos.get("left") ?? 0,
    top: pos.get("top") ?? 0,
    width: pos.get("width") ?? 0,
    height: pos.get("height") ?? 0,
    radius: pos.get("radius") ?? 0,
  });

  // Where the axis would go on the next visible frame. Peek and step share it,
  // so `settled()` never looks at a state the loop would not enter.
  const nextPos = (axis: (typeof AXES)[number], want: number): number => {
    const p = pos.get(axis) ?? 0;
    const gap = want - p;
    const dir = Math.sign(gap);
    if (dir === 0) return want;
    const v = ((vel.get(axis) ?? 0) + gap * STIFFNESS) * DAMPING;
    const next = p + v;
    // Never past the target, never more than MAX_STEP at once.
    if (Math.abs(want - next) >= Math.abs(gap)) return want;
    if (Math.abs(next - p) > MAX_STEP) return p + dir * MAX_STEP;
    return next;
  };

  return {
    step(target: Frame): Frame {
      for (const axis of AXES) {
        const want = finite(target[axis], pos.get(axis) ?? 0);
        const p = pos.get(axis) ?? 0;
        const next = nextPos(axis, want);
        // Land on the target with no velocity, or carry the decayed velocity.
        if (next === want) vel.set(axis, 0);
        else vel.set(axis, ((vel.get(axis) ?? 0) + (want - p) * STIFFNESS) * DAMPING);
        pos.set(axis, next);
      }
      return read();
    },
    current: read,
    place(frame: Frame): void {
      for (const axis of AXES) {
        pos.set(axis, finite(frame[axis], 0));
        vel.set(axis, 0);
      }
    },
    settled(target: Frame): boolean {
      for (const axis of AXES) {
        const want = finite(target[axis], pos.get(axis) ?? 0);
        const p = pos.get(axis) ?? 0;
        // Position within SETTLE_EPSILON, and the animation is over when the
        // next step would move under SETTLE_EPSILON too.
        if (Math.abs(want - p) > SETTLE_EPSILON) return false;
        if (Math.abs(p - nextPos(axis, want)) > SETTLE_EPSILON) return false;
      }
      return true;
    },
  };
}

/** Write a frame onto the blob element. */
export function paintBlob(element: HTMLElement, frame: Frame): void {
  element.style.left = `${frame.left}px`;
  element.style.top = `${frame.top}px`;
  element.style.width = `${frame.width}px`;
  element.style.height = `${frame.height}px`;
  element.style.borderRadius = `${frame.radius}px`;
}

function schedule(fn: () => void): number {
  if (typeof requestAnimationFrame === "function") return requestAnimationFrame(fn);
  return setTimeout(fn, 16) as unknown as number;
}

function cancelLoop(handle: number): void {
  if (typeof cancelAnimationFrame === "function") cancelAnimationFrame(handle);
  else clearTimeout(handle);
}

export type BlobMountOptions = {
  /** The `.theme-popover-glass` host inside the open popover. */
  host: HTMLElement;
  /** The element that holds the rows; rows are read from its children in order. */
  rows: ParentNode;
  /** Index of the row the blob rests on; -1 sends it away from the rows. */
  active: () => number;
  /** Reduced motion: place every frame, never run a loop. */
  instant?: boolean;
  /** Pointer in host coordinates, or null at rest. */
  pointer?: () => Point | null;
  /** Extra tokens; `radius`/`rowInset`/`stretch` default to DEFAULT_TOKENS. */
  tokens?: Partial<Tokens>;
};

export type BlobMount = {
  /** Recompute and paint one frame (also the loop's step). */
  sync(): void;
  /** Test hook: the geometry for the current inputs, before the spring. */
  shape(): BlobGeometry;
  /** Stop the loop and remove the element. */
  dispose(): void;
};

/**
 * Mount the blob into the popover host: creates `<span class="theme-blob">`
 * with its glass children and runs the spring loop from a pointer-driven
 * geometry.
 *
 * The module does not import the theme control; the caller passes the host and
 * the rows, so this stays testable and has no cycle with the component.
 */
export function mountThemeBlob(options: BlobMountOptions): BlobMount {
  const { host, rows, active, instant = false, pointer } = options;
  const tokens: Tokens = { ...DEFAULT_TOKENS, ...options.tokens };

  const blob = document.createElement("span");
  blob.className = "theme-blob glass-material";
  blob.setAttribute("aria-hidden", "true");
  for (const name of ["arc", "sheen"]) {
    const child = document.createElement("span");
    child.className = `theme-blob-${name}`;
    blob.appendChild(child);
  }
  host.appendChild(blob);
  const lens: GlassLens = mountGlassLens(blob);
  const paint = (frame: Frame) => {
    paintBlob(blob, frame);
    lens.paint();
  };

  const readShape = (): BlobGeometry => {
    const hostRect = host.getBoundingClientRect();
    const boxes = Array.from(rows.querySelectorAll<HTMLElement>(".theme-row, [role='radio']"));
    const rowBoxes: RowBox[] = boxes.map((row) => {
      const rect = row.getBoundingClientRect();
      return { x: rect.left - hostRect.left, y: rect.top - hostRect.top, height: rect.height };
    });
    return blobGeometry(
      { left: 0, top: 0, width: hostRect.width, height: hostRect.height },
      { rows: rowBoxes, active: active() },
      pointer?.() ?? null,
      tokens,
    );
  };

  const initial = geometryToFrame(readShape());
  if (instant) {
    // Reduced motion: place every frame, never request one.
    paint(initial);
    return {
      sync: () => paint(geometryToFrame(readShape())),
      shape: readShape,
      dispose: () => {
        lens.dispose();
        blob.remove();
      },
    };
  }

  const loop = createBlobLoop(paint);
  loop.start(initial, initial);

  return {
    sync: () => {
      loop.target(geometryToFrame(readShape()));
    },
    shape: readShape,
    dispose: () => {
      loop.dispose();
      lens.dispose();
      blob.remove();
    },
  };
}

export type BlobLoop = {
  /** Begin the loop from `origin`, heading for `target`. Idempotent. */
  start(origin: Frame, target: Frame): void;
  /** Point the spring at a new target without restarting the loop. */
  target(target: Frame): void;
  /** Place `frame` at once, no animation. */
  place(frame: Frame): void;
  stop(): void;
  running(): boolean;
  dispose(): void;
};

/**
 * The imperative animation loop. It starts on `start`, stops on its own once
 * the spring has settled (so a closed popover runs no frame) and stops on
 * `stop` or `dispose`; after `dispose` it never starts again.
 *
 * `paint` is called with every frame, and once more with the exact target on
 * settle, so the element never ends a fraction of a pixel away.
 */
export function createBlobLoop(paint: (frame: Frame) => void): BlobLoop {
  let spring: Spring | null = null;
  let target: Frame | null = null;
  let handle: number | null = null;
  let disposed = false;

  const clear = () => {
    if (handle !== null) cancelLoop(handle);
    handle = null;
  };

  const tick = () => {
    handle = null;
    if (disposed || !spring || !target) return;
    if (spring.settled(target)) {
      // The next frame would move under SETTLE_EPSILON: land exactly and stop.
      spring.place(target);
      paint(target);
      return;
    }
    paint(spring.step(target));
    handle = schedule(tick);
  };

  return {
    start(origin: Frame, next: Frame): void {
      if (disposed) return;
      if (!spring) spring = createSpring(origin);
      target = next;
      paint(spring.current());
      if (handle === null) handle = schedule(tick);
    },
    target(next: Frame): void {
      target = next;
      if (!disposed && spring && handle === null && !spring.settled(next)) handle = schedule(tick);
    },
    place(frame: Frame): void {
      clear();
      if (!spring) spring = createSpring(frame);
      else spring.place(frame);
      target = frame;
      paint(frame);
    },
    stop: clear,
    running(): boolean {
      return handle !== null;
    },
    dispose(): void {
      disposed = true;
      clear();
      spring = null;
      target = null;
    },
  };
}
