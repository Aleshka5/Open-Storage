import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import { ThemeControl } from "./ThemeControl";

const segments: Record<string, { left: number; width: number }> = {
  light: { left: 0, width: 58 },
  Dark: { left: 58, width: 70 },
  System: { left: 128, width: 96 },
};

function segmentBox(el: HTMLElement) {
  if (!el.classList.contains("theme-segment")) return null;
  return segments[el.textContent?.trim() ?? ""] ?? null;
}

describe("ThemeControl", () => {
  let host: HTMLDivElement;
  let root: Root;
  const metrics = ["offsetWidth", "offsetHeight", "offsetLeft"] as const;
  const previous = new Map<string, PropertyDescriptor | undefined>();

  afterEach(() => {
    act(() => root.unmount());
    host.remove();
    for (const key of metrics) {
      const descriptor = previous.get(key);
      if (descriptor) Object.defineProperty(HTMLElement.prototype, key, descriptor);
    }
  });

  function installMetrics() {
    for (const key of metrics) {
      previous.set(key, Object.getOwnPropertyDescriptor(HTMLElement.prototype, key));
      Object.defineProperty(HTMLElement.prototype, key, {
        configurable: true,
        get() {
          const box = segmentBox(this);
          if (box) {
            if (key === "offsetWidth") return box.width;
            if (key === "offsetHeight") return 36;
            return box.left;
          }
          return 0;
        },
      });
    }
  }

  function render(preference: "light" | "dark" | "system" = "dark") {
    host = document.createElement("div");
    document.body.appendChild(host);
    root = createRoot(host);
    const onChange = () => {};
    act(() => {
      root.render(<ThemeControl preference={preference} onChange={onChange} />);
    });
  }

  it("covers the selected word with one rounded glass", () => {
    installMetrics();
    render("light");
    const group = host.querySelector<HTMLElement>('[role="radiogroup"]');
    expect(group?.getAttribute("aria-label")).toBe("Theme");
    const radios = host.querySelectorAll<HTMLInputElement>('input[type="radio"]');
    expect(Array.from(radios, (radio) => radio.value)).toEqual(["light", "dark", "system"]);
    expect(radios[0]?.checked).toBe(true);

    const thumb = host.querySelector<HTMLElement>(".theme-thumb");
    const light = host.querySelector<HTMLElement>(".theme-segment:has(:checked)");
    expect(thumb?.getAttribute("data-liquid-glass")).toBe("material");
    expect(host.querySelectorAll("[data-liquid-glass]")).toHaveLength(1);
    expect(thumb?.querySelector(".theme-thumb-face")).not.toBeNull();
    expect(thumb?.style.borderRadius).toBe("12px");
    expect(thumb?.style.width).toBe(`${light?.offsetWidth}px`);
    expect(thumb?.style.transform).toContain("translate3d(0px");
    for (const label of host.querySelectorAll(".theme-segment")) {
      expect(thumb?.contains(label)).toBe(false);
    }

    act(() => {
      root.render(<ThemeControl preference="system" onChange={() => {}} />);
    });
    const system = host.querySelector<HTMLElement>(".theme-segment:has(:checked)");
    const next = host.querySelector<HTMLElement>(".theme-thumb");
    expect(host.querySelectorAll("[data-liquid-glass]")).toHaveLength(1);
    expect(system?.offsetWidth).not.toBe(light?.offsetWidth);
    expect(next?.style.width).toBe(`${system?.offsetWidth}px`);
    expect(next?.style.transform).toContain(`${system?.offsetLeft}px`);
    expect(next?.style.borderRadius).toBe("12px");
  });
});
