import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import { ThemeControl } from "./ThemeControl";

describe("ThemeControl", () => {
  let host: HTMLDivElement;
  let root: Root;

  afterEach(() => {
    act(() => root.unmount());
    host.remove();
  });

  function render(preference: "light" | "dark" | "system" = "dark") {
    host = document.createElement("div");
    document.body.appendChild(host);
    root = createRoot(host);
    const onChange = () => {};
    act(() => {
      root.render(<ThemeControl preference={preference} onChange={onChange} />);
    });
  }

  it("slides one liquid-glass thumb across the three states", () => {
    render("dark");
    const group = host.querySelector<HTMLElement>('[role="radiogroup"]');
    expect(group?.getAttribute("aria-label")).toBe("Theme");
    const radios = host.querySelectorAll<HTMLInputElement>('input[type="radio"]');
    expect(Array.from(radios, (radio) => radio.value)).toEqual(["light", "dark", "system"]);
    expect(radios[1]?.checked).toBe(true);

    const thumb = host.querySelector<HTMLElement>(".theme-thumb");
    expect(thumb?.getAttribute("data-liquid-glass")).toBe("material");
    expect(host.querySelectorAll("[data-liquid-glass]")).toHaveLength(1);
    expect(thumb?.querySelector(".theme-thumb-face")).not.toBeNull();
  });
});
