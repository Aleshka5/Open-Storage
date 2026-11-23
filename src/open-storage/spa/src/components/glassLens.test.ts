import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FILTER_AREA_CEILING, intersectingBackdrop, mountGlassLens } from "./glassLens";

describe("glass lens mount", () => {
  afterEach(() => {
    document.body.innerHTML = "";
    vi.unstubAllGlobals();
  });

  it("does not request an animation frame while painting", () => {
    const raf = vi.fn();
    vi.stubGlobal("requestAnimationFrame", raf);
    const host = document.createElement("div");
    host.getBoundingClientRect = () =>
      ({ left: 10, top: 10, width: 40, height: 40, right: 50, bottom: 50, x: 10, y: 10, toJSON() {} }) as DOMRect;
    document.body.append(host);
    const lens = mountGlassLens(host);
    lens.paint();
    expect(raf).not.toHaveBeenCalled();
    lens.dispose();
    expect(host.querySelector(".glass-lens")).toBeNull();
    expect(host.dataset.lensHost).toBeUndefined();
  });

  it("removes the bitmap under reduced transparency", () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query === "(prefers-reduced-transparency: reduce)",
      media: query,
      addEventListener() {},
      removeEventListener() {},
      addListener() {},
      removeListener() {},
    }));
    const host = document.createElement("div");
    host.getBoundingClientRect = () =>
      ({ left: 0, top: 0, width: 48, height: 48, right: 48, bottom: 48, x: 0, y: 0, toJSON() {} }) as DOMRect;
    document.body.append(host);
    const lens = mountGlassLens(host);
    lens.paint();
    expect(host.dataset.lens).toBe("off");
    expect(host.querySelector("canvas")).toBeNull();
    lens.dispose();
  });

  it("refuses a region above the filter-area ceiling", () => {
    const host = document.createElement("div");
    const side = Math.ceil(Math.sqrt(FILTER_AREA_CEILING) + 40);
    const rect = {
      left: 0,
      top: 0,
      width: side,
      height: side,
      right: side,
      bottom: side,
      x: 0,
      y: 0,
      toJSON() {},
    } as DOMRect;
    Object.defineProperty(host, "getBoundingClientRect", { configurable: true, value: () => rect });
    document.body.append(host);
    expect(host.getBoundingClientRect().width * host.getBoundingClientRect().height).toBeGreaterThan(FILTER_AREA_CEILING);
    const lens = mountGlassLens(host);
    lens.paint();
    expect(host.dataset.lens).toBe("clamped");
    expect(host.querySelector("canvas")).toBeNull();
    lens.dispose();
  });
});

describe("backdrop sample", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("keeps every stripe that intersects the lens box", () => {
    const skip = document.createElement("div");
    skip.dataset.lensHost = "";
    document.body.append(skip);
    const box = (left: number) =>
      ({
        left,
        top: 0,
        width: 12,
        height: 80,
        right: left + 12,
        bottom: 80,
        x: left,
        y: 0,
        toJSON() {},
      }) as DOMRect;
    for (let i = 0; i < 60; i += 1) {
      const stripe = document.createElement("div");
      stripe.className = "proof-stripe";
      stripe.style.backgroundColor = i % 2 === 0 ? "rgb(255, 40, 40)" : "rgb(40, 40, 255)";
      stripe.getBoundingClientRect = () => box(i * 12);
      document.body.append(stripe);
    }
    const label = document.createElement("span");
    label.className = "theme-row-label";
    label.textContent = "Light";
    const popover = document.createElement("div");
    popover.id = "theme-popover";
    popover.append(label);
    label.getBoundingClientRect = () => box(0);
    popover.getBoundingClientRect = () => box(0);
    document.body.append(popover);
    const hits = intersectingBackdrop(skip, 0, 0, 720, 80);
    expect(hits.filter((node) => node.classList.contains("proof-stripe"))).toHaveLength(60);
    expect(hits.some((node) => node.classList.contains("theme-row-label"))).toBe(false);
  });
});

describe("geometry is not transitioned", () => {
  const css = readFileSync("src/components/ThemeControl.css", "utf8");

  it("has no transition or keyframe for left, top, width, height, or border-radius", () => {
    const banned = ["left", "top", "width", "height", "border-radius"];
    const transitionBlocks = css.match(/transition\s*:[^;}]+/g) ?? [];
    for (const block of transitionBlocks) {
      for (const property of banned) {
        expect(block, block).not.toMatch(new RegExp(`(^|[\\s,])${property}\\b`));
      }
    }
    const frames = css.match(/@keyframes[\s\S]*?\n\}/g) ?? [];
    for (const frame of frames) {
      for (const property of banned) {
        expect(frame, frame).not.toMatch(new RegExp(`(^|[\\s{;])${property}\\s*:`));
      }
    }
  });
});
