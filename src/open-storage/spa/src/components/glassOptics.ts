/**
 * Optical glass for the theme control (ADR-0005).
 *
 * Chromium will not refract a backdrop through `backdrop-filter: url(#svg)`,
 * so the lens samples the backdrop and displaces it here. The map is the
 * `feDisplacementMap` contract: 128 is no shift, R is horizontal, G is
 * vertical, and the shift is `(channel - 128) / 128 * scale`. The height
 * field is a convex lens plus two octaves of value noise (the `feTurbulence`
 * stand-in). Scale never exceeds the ceiling the caller passes.
 */

export type Rgba = Uint8ClampedArray;

export type Optics = {
  /** Pixel shift at the rim, already clamped to `ceiling`. */
  strength: number;
  /** Extra rim shift for the red/blue split, in the same pixels. */
  dispersion: number;
  /** 0..1 paper wash at the centre, where the labels sit. */
  washCenter: number;
  /** 0..1 paper wash at the rim, where the bend should stay visible. */
  washEdge: number;
  ceiling: number;
};

export const FALLBACK_OPTICS: Optics = {
  strength: 14,
  dispersion: 1.6,
  washCenter: 0.72,
  washEdge: 0.1,
  ceiling: 18,
};

/** Largest backdrop a lens may rasterise, in CSS pixels. The viewport is not a lens. */
export const FILTER_AREA_CEILING = 240 * 200;

const AXES = 4;

function clamp(value: number, min: number, max: number): number {
  if (max < min) return (min + max) / 2;
  return value < min ? min : value > max ? max : value;
}

function hash(ix: number, iy: number): number {
  const n = Math.sin(ix * 127.1 + iy * 311.7) * 43758.5453;
  return n - Math.floor(n);
}

/** Smooth value noise in [-1, 1]. */
function noise(x: number, y: number): number {
  const x0 = Math.floor(x);
  const y0 = Math.floor(y);
  const tx = x - x0;
  const ty = y - y0;
  const sx = tx * tx * (3 - 2 * tx);
  const sy = ty * ty * (3 - 2 * ty);
  const v00 = hash(x0, y0);
  const v10 = hash(x0 + 1, y0);
  const v01 = hash(x0, y0 + 1);
  const v11 = hash(x0 + 1, y0 + 1);
  const a = v00 + (v10 - v00) * sx;
  const b = v01 + (v11 - v01) * sx;
  return (a + (b - a) * sy) * 2 - 1;
}

/** Two octaves. This is the turbulence term mixed into the lens height. */
export function turbulence(x: number, y: number): number {
  return noise(x, y) * 0.65 + noise(x * 2.07 + 8.2, y * 2.07 - 3.1) * 0.35;
}

function readNumber(style: CSSStyleDeclaration, name: string, fallback: number): number {
  const raw = style.getPropertyValue(name);
  const value = Number.parseFloat(raw);
  return Number.isFinite(value) ? value : fallback;
}

/**
 * Tokens on `:root`. `prefers-reduced-transparency` zeroes the bend and the
 * split; the ceiling still applies to any other caller.
 */
export function readOptics(style: CSSStyleDeclaration, reducedTransparency: boolean): Optics {
  const ceiling = Math.max(0, readNumber(style, "--glass-strength-ceiling", FALLBACK_OPTICS.ceiling));
  const authored = readNumber(style, "--glass-strength", FALLBACK_OPTICS.strength);
  const dispersion = readNumber(style, "--glass-dispersion", FALLBACK_OPTICS.dispersion);
  return {
    ceiling,
    strength: reducedTransparency ? 0 : clamp(authored, 0, ceiling),
    dispersion: reducedTransparency ? 0 : Math.max(0, dispersion),
    washCenter: clamp(readNumber(style, "--glass-wash-center", FALLBACK_OPTICS.washCenter), 0, 1),
    washEdge: clamp(readNumber(style, "--glass-wash-edge", FALLBACK_OPTICS.washEdge), 0, 1),
  };
}

export function prefersReducedTransparency(): boolean {
  return (
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-transparency: reduce)").matches
  );
}

/**
 * Convex-lens offset at a dest pixel, in pixels. The centre is still; the rim
 * pulls samples inward (the marble magnifies). Noise breaks the perfect
 * circle so the edge reads as liquid. The vector is clamped to `ceiling`.
 */
export function lensOffset(
  x: number,
  y: number,
  width: number,
  height: number,
  strength: number,
  ceiling: number,
): { dx: number; dy: number; dist: number } {
  const cap = Math.max(0, ceiling);
  const mag = clamp(strength, 0, cap);
  if (mag === 0 || width < 2 || height < 2) return { dx: 0, dy: 0, dist: 0 };
  if (!Number.isFinite(x) || !Number.isFinite(y)) return { dx: 0, dy: 0, dist: 0 };
  const rx = width / 2;
  const ry = height / 2;
  const nx = (x + 0.5 - rx) / rx;
  const ny = (y + 0.5 - ry) / ry;
  const dist = Math.min(1, Math.hypot(nx, ny));
  if (dist >= 1) return { dx: 0, dy: 0, dist };
  const z = Math.sqrt(Math.max(0, 1 - dist * dist));
  // The bulge lives inside. Across the outer few pixels the shift, including
  // the liquid term, falls to 0 so the silhouette is one smooth curve.
  const edgePx = (1 - dist) * Math.min(rx, ry);
  const rimFade = clamp(edgePx / 6, 0, 1);
  const falloff = (1 - z) * rimFade;
  const wobbleAmp = Math.min(0.2, cap * 0.012);
  const wobble = turbulence(x * 0.15, y * 0.15) * wobbleAmp * falloff;
  const wobbleY = turbulence(x * 0.15 + 19, y * 0.15) * wobbleAmp * falloff;
  let dx = (nx / (dist || 1)) * mag * falloff + wobble;
  let dy = (ny / (dist || 1)) * mag * falloff + wobbleY;
  const len = Math.hypot(dx, dy);
  if (len > cap && len > 0) {
    dx = (dx / len) * cap;
    dy = (dy / len) * cap;
  }
  return { dx, dy, dist };
}

/**
 * `feDisplacementMap` image. R and G carry the offset, 128 is neutral.
 * `scale` is the map's full-scale shift and must be the ceiling, so a channel
 * of 0 or 255 is exactly `±scale` px.
 */
export function displacementMap(
  width: number,
  height: number,
  strength: number,
  ceiling: number,
): Rgba {
  const w = Math.max(0, Math.floor(width));
  const h = Math.max(0, Math.floor(height));
  const map = new Uint8ClampedArray(w * h * AXES);
  const scale = Math.max(0, ceiling);
  for (let y = 0; y < h; y += 1) {
    for (let x = 0; x < w; x += 1) {
      const { dx, dy } = lensOffset(x, y, w, h, strength, scale);
      const i = (y * w + x) * AXES;
      const encode = (delta: number) => clamp(Math.round(128 + (scale === 0 ? 0 : (delta / scale) * 128)), 0, 255);
      map[i] = encode(dx);
      map[i + 1] = encode(dy);
      map[i + 2] = 128;
      map[i + 3] = 255;
    }
  }
  return map;
}

function sample(
  src: Rgba,
  sw: number,
  sh: number,
  x: number,
  y: number,
): [number, number, number, number] {
  if (sw <= 0 || sh <= 0) return [0, 0, 0, 255];
  const cx = clamp(x, 0, sw - 1);
  const cy = clamp(y, 0, sh - 1);
  const x0 = Math.floor(cx);
  const y0 = Math.floor(cy);
  const x1 = Math.min(sw - 1, x0 + 1);
  const y1 = Math.min(sh - 1, y0 + 1);
  const tx = cx - x0;
  const ty = cy - y0;
  const at = (px: number, py: number) => (py * sw + px) * AXES;
  const i00 = at(x0, y0);
  const i10 = at(x1, y0);
  const i01 = at(x0, y1);
  const i11 = at(x1, y1);
  const mix = (c: number) => {
    const top = src[i00 + c] + (src[i10 + c] - src[i00 + c]) * tx;
    const bot = src[i01 + c] + (src[i11 + c] - src[i01 + c]) * tx;
    return top + (bot - top) * ty;
  };
  return [mix(0), mix(1), mix(2), mix(3)];
}

export type Paper = { r: number; g: number; b: number };

/** How many samples each output pixel averages. Stairs on a hard edge become a curve. */
export const SUPERSAMPLE = 2;

/**
 * Signed distance to a rounded rectangle, in pixels. Negative inside.
 * `radius` is clamped to the box, so a circle and a capsule are the same call.
 */
export function roundedRectSdf(
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
): number {
  const r = Math.max(0, Math.min(radius, width / 2, height / 2));
  const hx = width / 2;
  const hy = height / 2;
  const qx = Math.abs(x - hx) - (hx - r);
  const qy = Math.abs(y - hy) - (hy - r);
  return Math.hypot(Math.max(qx, 0), Math.max(qy, 0)) + Math.min(Math.max(qx, qy), 0) - r;
}

/**
 * Coverage of the lens at a dest-pixel centre. 1 inside, 0 outside, and a
 * ramp about 4px wide so a CSS-scaled edge is not a stairstep.
 */
export function lensCoverage(
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
): number {
  const sdf = roundedRectSdf(x, y, width, height, radius);
  const aa = 4;
  return clamp(0.5 - sdf / (2 * aa), 0, 1);
}

function mapShift(
  map: Rgba,
  dw: number,
  dh: number,
  x: number,
  y: number,
  scale: number,
): { dx: number; dy: number } {
  if (scale === 0 || dw < 1 || dh < 1) return { dx: 0, dy: 0 };
  const cx = clamp(x, 0, dw - 1);
  const cy = clamp(y, 0, dh - 1);
  const x0 = Math.floor(cx);
  const y0 = Math.floor(cy);
  const x1 = Math.min(dw - 1, x0 + 1);
  const y1 = Math.min(dh - 1, y0 + 1);
  const tx = cx - x0;
  const ty = cy - y0;
  const at = (px: number, py: number, channel: number) => map[(py * dw + px) * AXES + channel];
  const mix = (channel: number) => {
    const top = at(x0, y0, channel) + (at(x1, y0, channel) - at(x0, y0, channel)) * tx;
    const bot = at(x0, y1, channel) + (at(x1, y1, channel) - at(x0, y1, channel)) * tx;
    return top + (bot - top) * ty;
  };
  return { dx: ((mix(0) - 128) / 128) * scale, dy: ((mix(1) - 128) / 128) * scale };
}

/**
 * Displace `source` into a `dw × dh` image. `source` is the backdrop with
 * `pad` pixels of context on every side. `scale` is the feDisplacementMap
 * scale (the ceiling). Each output pixel is the mean of a 2×2 grid, and the
 * alpha follows the rounded lens so the rim is a curve rather than a hard
 * rectangle. Dispersion samples red a little further along the bend and blue
 * a little less, and only where the rim is already bending.
 */
export function applyDisplacementMap(
  source: Rgba,
  sw: number,
  sh: number,
  map: Rgba,
  dw: number,
  dh: number,
  pad: number,
  scale: number,
  dispersion: number,
  wash: Pick<Optics, "washCenter" | "washEdge">,
  paper: Paper,
  radius: number = Math.min(Math.max(dw, 0), Math.max(dh, 0)) / 2,
): Rgba {
  const out = new Uint8ClampedArray(Math.max(0, dw) * Math.max(0, dh) * AXES);
  const full = Math.max(0, scale);
  const samples = SUPERSAMPLE * SUPERSAMPLE;
  for (let y = 0; y < dh; y += 1) {
    for (let x = 0; x < dw; x += 1) {
      let accR = 0;
      let accG = 0;
      let accB = 0;
      let accA = 0;
      for (let oy = 0; oy < SUPERSAMPLE; oy += 1) {
        for (let ox = 0; ox < SUPERSAMPLE; ox += 1) {
          const px = x + (ox + 0.5) / SUPERSAMPLE;
          const py = y + (oy + 0.5) / SUPERSAMPLE;
          const cover = lensCoverage(px, py, dw, dh, radius);
          const shift = mapShift(map, dw, dh, px, py, full);
          // The coverage ramp is the silhouette. Shift dies there; the bulge stays inside.
          const sdf = roundedRectSdf(px, py, dw, dh, radius);
          const silhouette = clamp(-sdf / 6, 0, 1);
          shift.dx *= silhouette;
          shift.dy *= silhouette;
          const dist = Math.min(1, Math.hypot(shift.dx, shift.dy) / (full || 1));
          const chroma = dispersion * dist;
          const bend = full === 0 ? 0 : chroma / full;
          const red = sample(source, sw, sh, px + pad + shift.dx * (1 + bend), py + pad + shift.dy * (1 + bend));
          const green = sample(source, sw, sh, px + pad + shift.dx, py + pad + shift.dy);
          const blue = sample(source, sw, sh, px + pad + shift.dx * (1 - bend), py + pad + shift.dy * (1 - bend));
          const gx = dw > 1 ? (px / dw) * 2 - 1 : 0;
          const gy = dh > 1 ? (py / dh) * 2 - 1 : 0;
          const geom = Math.min(1, Math.hypot(gx, gy));
          const washT = wash.washCenter + (wash.washEdge - wash.washCenter) * geom;
          const cr = clamp(red[0] * (1 - washT) + paper.r * washT, 0, 255);
          const cg = clamp(green[1] * (1 - washT) + paper.g * washT, 0, 255);
          const cb = clamp(blue[2] * (1 - washT) + paper.b * washT, 0, 255);
          accR += cr * cover;
          accG += cg * cover;
          accB += cb * cover;
          accA += cover;
        }
      }
      const oi = (y * dw + x) * AXES;
      const alpha = accA / samples;
      out[oi] = alpha > 0 ? clamp(accR / accA, 0, 255) : 0;
      out[oi + 1] = alpha > 0 ? clamp(accG / accA, 0, 255) : 0;
      out[oi + 2] = alpha > 0 ? clamp(accB / accA, 0, 255) : 0;
      out[oi + 3] = clamp(alpha * 255, 0, 255);
    }
  }
  return out;
}

/** sRGB relative luminance. */
export function channelLuma(channel: number): number {
  const c = clamp(channel, 0, 255) / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

export function luminance(r: number, g: number, b: number): number {
  return 0.2126 * channelLuma(r) + 0.7152 * channelLuma(g) + 0.0722 * channelLuma(b);
}

/** WCAG contrast ratio. The brand book states the faces; 4.5 is the text rule applied over them. */
export function contrastRatio(fg: Paper, bg: Paper): number {
  const a = luminance(fg.r, fg.g, fg.b);
  const b = luminance(bg.r, bg.g, bg.b);
  const [hi, lo] = a > b ? [a, b] : [b, a];
  return (hi + 0.05) / (lo + 0.05);
}

export function parseColor(input: string): Paper | null {
  const text = input.trim();
  const hex = /^#([\da-f]{3}|[\da-f]{6})$/i.exec(text);
  if (hex) {
    const raw = hex[1];
    const full = raw.length === 3 ? raw.replace(/./g, (c) => c + c) : raw;
    return {
      r: Number.parseInt(full.slice(0, 2), 16),
      g: Number.parseInt(full.slice(2, 4), 16),
      b: Number.parseInt(full.slice(4, 6), 16),
    };
  }
  const rgb = /^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/i.exec(text);
  if (!rgb) return null;
  return { r: Number(rgb[1]), g: Number(rgb[2]), b: Number(rgb[3]) };
}

/** Paper mixed over an arbitrary backdrop. Used to bound text contrast. */
export function mixPaper(paper: Paper, backdrop: Paper, wash: number): Paper {
  const t = clamp(wash, 0, 1);
  return {
    r: paper.r * t + backdrop.r * (1 - t),
    g: paper.g * t + backdrop.g * (1 - t),
    b: paper.b * t + backdrop.b * (1 - t),
  };
}
