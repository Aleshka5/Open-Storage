/**
 * Paints one lens into a host: a backdrop sample, then the displacement map
 * from `glassOptics`. The region is the host's border box plus the ceiling
 * of context the bend can reach. Nothing here calls `requestAnimationFrame`;
 * the theme blob's loop is the only frame owner, and it calls `paint`.
 */

import {
  FILTER_AREA_CEILING,
  applyDisplacementMap,
  displacementMap,
  parseColor,
  prefersReducedTransparency,
  readOptics,
  type Paper,
} from "./glassOptics";

export { FILTER_AREA_CEILING };

export type GlassLens = {
  paint(): void;
  dispose(): void;
};

const PAPER_FALLBACK: Paper = { r: 28, g: 27, b: 25 };

function cssNumber(value: string): number {
  const n = Number.parseFloat(value);
  return Number.isFinite(n) ? n : 0;
}

function paperFrom(style: CSSStyleDeclaration): Paper {
  return parseColor(style.getPropertyValue("--paper-raised")) ?? PAPER_FALLBACK;
}

/** Two box passes. Radius is in source pixels. */
function soften(data: Uint8ClampedArray, width: number, height: number, radius: number): void {
  if (radius < 1 || width < 2 || height < 2) return;
  const tmp = new Uint8ClampedArray(data.length);
  const blur = (input: Uint8ClampedArray, output: Uint8ClampedArray, horizontal: boolean) => {
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        let r = 0;
        let g = 0;
        let b = 0;
        let a = 0;
        let n = 0;
        for (let k = -radius; k <= radius; k += 1) {
          const sx = horizontal ? Math.min(width - 1, Math.max(0, x + k)) : x;
          const sy = horizontal ? y : Math.min(height - 1, Math.max(0, y + k));
          const i = (sy * width + sx) * 4;
          r += input[i];
          g += input[i + 1];
          b += input[i + 2];
          a += input[i + 3];
          n += 1;
        }
        const o = (y * width + x) * 4;
        output[o] = r / n;
        output[o + 1] = g / n;
        output[o + 2] = b / n;
        output[o + 3] = a / n;
      }
    }
  };
  blur(data, tmp, true);
  blur(tmp, data, false);
  blur(data, tmp, true);
  blur(tmp, data, false);
}

function intersects(a: DOMRect, left: number, top: number, right: number, bottom: number): boolean {
  return a.right > left && a.left < right && a.bottom > top && a.top < bottom;
}

function ownText(el: Element): string {
  let text = "";
  for (const child of el.childNodes) {
    if (child.nodeType === Node.TEXT_NODE) text += child.textContent ?? "";
  }
  return text.replace(/\s+/g, " ").trim();
}

const SKIP_BACKDROP = ".theme-control, #theme-popover, [data-lens-host]";

/**
 * Every element that actually intersects the lens box. Nothing is dropped
 * once it intersects: a cap here is what turned the field into a few
 * rectangles. The lens, the popover (its labels stay sharp above the
 * bitmap), and the wordmark are not part of the photograph.
 */
export function intersectingBackdrop(
  skip: Element,
  left: number,
  top: number,
  right: number,
  bottom: number,
): HTMLElement[] {
  const found: HTMLElement[] = [];
  const nodes = document.body.querySelectorAll<HTMLElement>("*");
  for (const node of nodes) {
    if (node === skip || skip.contains(node)) continue;
    if (node.closest(SKIP_BACKDROP)) continue;
    const style = getComputedStyle(node);
    if (style.display === "none" || style.visibility === "hidden") continue;
    const opacity = Number.parseFloat(style.opacity);
    if (Number.isFinite(opacity) && opacity <= 0) continue;
    const box = node.getBoundingClientRect();
    if (box.width < 1 || box.height < 1) continue;
    if (!intersects(box, left, top, right, bottom)) continue;
    found.push(node);
  }
  return found;
}

/**
 * Draw whatever is actually behind the lens: fills and the header diamond.
 * Labels are not painted into the bitmap.
 */
export function rasterBackdrop(
  ctx: CanvasRenderingContext2D,
  originX: number,
  originY: number,
  width: number,
  height: number,
  skip: Element,
): void {
  const rootStyle = getComputedStyle(document.documentElement);
  const paper = paperFrom(rootStyle);
  const accent = parseColor(rootStyle.getPropertyValue("--accent")) ?? { r: 201, g: 121, b: 79 };
  const ink = parseColor(rootStyle.getPropertyValue("--ink")) ?? { r: 244, g: 239, b: 230 };
  ctx.fillStyle = `rgb(${paper.r} ${paper.g} ${paper.b})`;
  ctx.fillRect(0, 0, width, height);

  const nodes = intersectingBackdrop(skip, originX, originY, originX + width, originY + height);
  for (const node of nodes) {
    const style = getComputedStyle(node);
    const box = node.getBoundingClientRect();
    const x = box.left - originX;
    const y = box.top - originY;
    const bg = parseColor(style.backgroundColor);
    if (bg && style.backgroundColor !== "rgba(0, 0, 0, 0)") {
      ctx.fillStyle = style.backgroundColor;
      ctx.fillRect(x, y, box.width, box.height);
    }
    if (node.classList.contains("brand-mark") || node.classList.contains("proof-mark")) {
      drawDiamond(ctx, x, y, box.width, box.height, style.color || `rgb(${ink.r} ${ink.g} ${ink.b})`, accent);
    }
    if (node.closest(".brand-name")) continue;
    const text = ownText(node);
    const textStartsInside = box.left >= originX - 2 && box.left <= originX + width;
    if (!text || !textStartsInside) continue;
    ctx.fillStyle = style.color;
    ctx.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    ctx.textBaseline = "middle";
    const padX = cssNumber(style.paddingLeft);
    ctx.fillText(text, x + padX, y + box.height / 2, Math.max(0, box.width - padX));
  }
}

function drawDiamond(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  stroke: string,
  dot: Paper,
): void {
  ctx.save();
  ctx.translate(x, y);
  ctx.scale(width / 32, height / 32);
  ctx.beginPath();
  ctx.moveTo(16, 3);
  ctx.lineTo(29, 16);
  ctx.lineTo(16, 29);
  ctx.lineTo(3, 16);
  ctx.closePath();
  ctx.strokeStyle = stroke;
  ctx.lineWidth = 1.75;
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(16, 16, 3.2, 0, Math.PI * 2);
  ctx.fillStyle = `rgb(${dot.r} ${dot.g} ${dot.b})`;
  ctx.fill();
  ctx.restore();
}

/**
 * Mount a lens canvas on `host`. `active` false (the plate while the popover
 * is open, or reduced transparency) removes the bitmap: the solid face is CSS.
 */
export function mountGlassLens(host: HTMLElement, active: () => boolean = () => true): GlassLens {
  host.dataset.lensHost = "true";
  let canvas: HTMLCanvasElement | null = null;

  const ensure = (): HTMLCanvasElement | null => {
    if (!canvas) {
      canvas = document.createElement("canvas");
      canvas.className = "glass-lens";
      canvas.setAttribute("aria-hidden", "true");
      host.prepend(canvas);
    }
    return canvas;
  };

  const remove = () => {
    canvas?.remove();
    canvas = null;
  };

  return {
    paint() {
      const reduced = prefersReducedTransparency();
      const show = active() && !reduced;
      host.dataset.lens = show ? "on" : "off";
      if (!show) {
        remove();
        return;
      }
      const rect = host.getBoundingClientRect();
      if (rect.width < 2 || rect.height < 2) return;
      if (rect.width * rect.height > FILTER_AREA_CEILING) {
        host.dataset.lens = "clamped";
        remove();
        return;
      }
      const node = ensure();
      if (!node) return;
      const ctx = node.getContext("2d", { willReadFrequently: true });
      if (!ctx) return;
      const style = getComputedStyle(document.documentElement);
      const optics = readOptics(style, false);
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const pad = Math.ceil(optics.ceiling + 2);
      const srcW = Math.max(1, Math.ceil((rect.width + pad * 2) * dpr));
      const srcH = Math.max(1, Math.ceil((rect.height + pad * 2) * dpr));
      const destW = Math.max(1, Math.ceil(rect.width * dpr));
      const destH = Math.max(1, Math.ceil(rect.height * dpr));
      const padPx = Math.round(pad * dpr);

      const sample = document.createElement("canvas");
      sample.width = srcW;
      sample.height = srcH;
      const sampleCtx = sample.getContext("2d", { willReadFrequently: true });
      if (!sampleCtx) return;
      sampleCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
      rasterBackdrop(sampleCtx, rect.left - pad, rect.top - pad, rect.width + pad * 2, rect.height + pad * 2, host);
      const source = sampleCtx.getImageData(0, 0, srcW, srcH);
      // Hard rect edges become ramps, so the displacement bends them as curves.
      soften(source.data, srcW, srcH, 2);

      const strength = optics.strength * dpr;
      const ceiling = optics.ceiling * dpr;
      const map = displacementMap(destW, destH, strength, ceiling);
      const radiusCss = Number.parseFloat(getComputedStyle(host).borderRadius);
      const radius = (Number.isFinite(radiusCss) ? radiusCss : Math.min(rect.width, rect.height) / 2) * dpr;
      const image = applyDisplacementMap(
        source.data,
        srcW,
        srcH,
        map,
        destW,
        destH,
        padPx,
        ceiling,
        optics.dispersion * dpr,
        optics,
        paperFrom(style),
        radius,
      );
      node.width = destW;
      node.height = destH;
      const out = node.getContext("2d");
      if (!out) return;
      out.putImageData(new ImageData(new Uint8ClampedArray(image), destW, destH), 0, 0);
    },
    dispose() {
      remove();
      delete host.dataset.lensHost;
      delete host.dataset.lens;
    },
  };
}
