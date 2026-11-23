import { describe, expect, it } from "vitest";
import {
  FALLBACK_OPTICS,
  applyDisplacementMap,
  contrastRatio,
  displacementMap,
  lensCoverage,
  lensOffset,
  mixPaper,
  parseColor,
  readOptics,
  turbulence,
} from "./glassOptics";

const paper = { r: 42, g: 40, b: 36 };
const ink = { r: 244, g: 239, b: 230 };
const lightInk = { r: 26, g: 22, b: 18 };
const lightPaper = { r: 255, g: 253, b: 248 };

function stripe(width: number, height: number): Uint8ClampedArray {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const i = (y * width + x) * 4;
      const on = Math.floor(x / 4) % 2 === 0;
      data[i] = on ? 220 : 20;
      data[i + 1] = on ? 40 : 180;
      data[i + 2] = on ? 40 : 40;
      data[i + 3] = 255;
    }
  }
  return data;
}

describe("lens offset", () => {
  it("is still at the centre and bends toward the rim", () => {
    const mid = lensOffset(16, 16, 32, 32, 14, 18);
    const rim = lensOffset(4, 16, 32, 32, 14, 18);
    expect(Math.hypot(mid.dx, mid.dy)).toBeLessThan(1.5);
    expect(Math.hypot(rim.dx, rim.dy)).toBeGreaterThan(Math.hypot(mid.dx, mid.dy));
  });

  it("never exceeds the ceiling, even when the caller asks for more", () => {
    const offset = lensOffset(2, 8, 40, 24, 100, 18);
    expect(Math.hypot(offset.dx, offset.dy)).toBeLessThanOrEqual(18 + 1e-6);
  });

  it("does not displace the outer rim by the full ceiling", () => {
    const outer = lensOffset(0, 16, 32, 32, 14, 18);
    expect(Math.hypot(outer.dx, outer.dy)).toBeLessThan(2);
    const bulge = lensOffset(8, 16, 32, 32, 14, 18);
    expect(Math.hypot(bulge.dx, bulge.dy)).toBeGreaterThan(Math.hypot(outer.dx, outer.dy));
    expect(Math.hypot(bulge.dx, bulge.dy)).toBeLessThanOrEqual(18);
  });

  it("is zero when the strength is zero or the box is degenerate", () => {
    expect(lensOffset(4, 4, 20, 20, 0, 18)).toEqual({ dx: 0, dy: 0, dist: 0 });
    expect(lensOffset(0, 0, 0, 10, 14, 18).dx).toBe(0);
    expect(Number.isFinite(lensOffset(Number.NaN, 2, 10, 10, 14, 18).dx)).toBe(true);
  });
});

describe("displacement map", () => {
  it("encodes the feDisplacementMap neutral at 128 and round-trips the shift", () => {
    const map = displacementMap(24, 24, 14, 18);
    expect(map[(12 * 24 + 12) * 4]).toBeGreaterThan(110);
    expect(map[(12 * 24 + 12) * 4]).toBeLessThan(146);
    const edge = (12 * 24 + 2) * 4;
    const dx = ((map[edge] - 128) / 128) * 18;
    expect(Math.abs(dx)).toBeGreaterThan(2);
    expect(Math.abs(dx)).toBeLessThanOrEqual(18);
  });

  it("is neutral everywhere when strength is zero", () => {
    const map = displacementMap(8, 8, 0, 18);
    for (let i = 0; i < map.length; i += 4) {
      expect(map[i]).toBe(128);
      expect(map[i + 1]).toBe(128);
    }
  });
});

describe("refraction", () => {
  const pad = 18;
  const dw = 32;
  const dh = 32;
  const sw = dw + pad * 2;
  const sh = dh + pad * 2;

  function scene(): Uint8ClampedArray {
    return stripe(sw, sh);
  }

  it("copies the backdrop when the scale is zero", () => {
    const source = scene();
    const map = displacementMap(dw, dh, 0, 18);
    const out = applyDisplacementMap(source, sw, sh, map, dw, dh, pad, 0, 0, { washCenter: 0, washEdge: 0 }, paper);
    const straight = (x: number, y: number) => source[((y + pad) * sw + (x + pad)) * 4];
    expect(out[(8 * dw + 6) * 4]).toBeCloseTo(straight(6, 8), 0);
  });

  it("moves a high-frequency stripe so a rim pixel differs from the unbent sample", () => {
    const source = scene();
    const map = displacementMap(dw, dh, 14, 18);
    const out = applyDisplacementMap(source, sw, sh, map, dw, dh, pad, 18, 1.6, { washCenter: 0, washEdge: 0 }, paper);
    const x = 4;
    const y = 16;
    const bent = out[(y * dw + x) * 4];
    const straight = source[((y + pad) * sw + (x + pad)) * 4];
    expect(bent).not.toBe(straight);
  });

  it("splits red and blue at the rim", () => {
    const source = scene();
    const map = displacementMap(dw, dh, 14, 18);
    const out = applyDisplacementMap(source, sw, sh, map, dw, dh, pad, 18, 6, { washCenter: 0, washEdge: 0 }, paper);
    const i = (16 * dw + 4) * 4;
    expect(out[i]).not.toBe(out[i + 2]);
  });

  it("keeps the centre wash heavier than the rim so labels sit on paper", () => {
    const source = new Uint8ClampedArray(sw * sh * 4);
    const map = displacementMap(dw, dh, 14, 18);
    const out = applyDisplacementMap(
      source,
      sw,
      sh,
      map,
      dw,
      dh,
      pad,
      18,
      0,
      { washCenter: 0.7, washEdge: 0.2 },
      { r: 255, g: 255, b: 255 },
    );
    const center = out[(16 * dw + 16) * 4];
    const rim = out[(16 * dw + 3) * 4];
    expect(center).toBeGreaterThan(rim);
  });

  it("is opaque inside the lens and feathered to clear across the rim", () => {
    const source = scene();
    const map = displacementMap(dw, dh, 0, 18);
    const out = applyDisplacementMap(source, sw, sh, map, dw, dh, pad, 0, 0, { washCenter: 0, washEdge: 0 }, paper, 16);
    const alpha = (x: number, y: number) => out[(y * dw + x) * 4 + 3];
    expect(alpha(16, 16)).toBe(255);
    expect(alpha(0, 0)).toBe(0);
    const rim = alpha(0, 16);
    expect(rim).toBeGreaterThan(8);
    expect(rim).toBeLessThan(250);
    expect(lensCoverage(16, 16, 32, 32, 16)).toBe(1);
    expect(lensCoverage(0, 0, 32, 32, 16)).toBe(0);
  });
});

describe("turbulence", () => {
  it("stays inside [-1, 1] and is not a flat field", () => {
    const a = turbulence(1.2, 3.4);
    const b = turbulence(8.2, 3.4);
    expect(Math.abs(a)).toBeLessThanOrEqual(1);
    expect(a).not.toBe(b);
  });
});

describe("optics tokens", () => {
  function style(values: Record<string, string>): CSSStyleDeclaration {
    return {
      getPropertyValue: (name: string) => values[name] ?? "",
    } as CSSStyleDeclaration;
  }

  it("clamps an authored strength to the ceiling and zeroes it under reduced transparency", () => {
    const loud = readOptics(
      style({
        "--glass-strength": "40",
        "--glass-strength-ceiling": "18",
        "--glass-dispersion": "1.6",
        "--glass-wash-center": "0.5",
        "--glass-wash-edge": "0.22",
      }),
      false,
    );
    expect(loud.strength).toBe(18);
    expect(loud.ceiling).toBe(18);
    const quiet = readOptics(
      style({
        "--glass-strength": "14",
        "--glass-strength-ceiling": "18",
        "--glass-dispersion": "1.6",
      }),
      true,
    );
    expect(quiet.strength).toBe(0);
    expect(quiet.dispersion).toBe(0);
  });

  it("falls back when the tokens are missing", () => {
    const optics = readOptics(style({}), false);
    expect(optics.strength).toBe(FALLBACK_OPTICS.strength);
    expect(optics.ceiling).toBe(FALLBACK_OPTICS.ceiling);
  });
});

describe("text contrast over the wash", () => {
  it("keeps both inks at 4.5:1 against the centre wash on black and on white", () => {
    const wash = 0.72;
    const darkFg = ink;
    const darkPaper = { r: 42, g: 40, b: 36 };
    for (const backdrop of [
      { r: 0, g: 0, b: 0 },
      { r: 255, g: 255, b: 255 },
    ]) {
      expect(contrastRatio(darkFg, mixPaper(darkPaper, backdrop, wash))).toBeGreaterThanOrEqual(4.5);
      expect(contrastRatio(lightInk, mixPaper(lightPaper, backdrop, wash))).toBeGreaterThanOrEqual(4.5);
    }
  });
});

describe("parseColor", () => {
  it("reads hex and rgb", () => {
    expect(parseColor("#1c1b19")).toEqual({ r: 28, g: 27, b: 25 });
    expect(parseColor("rgb(255, 253, 248)")).toEqual({ r: 255, g: 253, b: 248 });
    expect(parseColor("nope")).toBeNull();
  });
});
