import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeControl } from "./components/ThemeControl";
import type { Preference } from "./theme";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
// JS test harness only: a pointer that leaves a passivated page learns it moved.
const setPointer = (node: HTMLElement, type: string, related: Element) => {
  node.dispatchEvent(new PointerEvent(type, { bubbles: true, relatedTarget: related }));
};

let host: HTMLElement;
let root: Root;

/**
 * The control takes the `Theme` slot in the header. jsdom cannot focus a button
 * nested in a button, so the host is a plain element here and the round glass
 * face around the control is checked in the browser instead.
 */
function render(preference: Preference, onChange = vi.fn()) {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  act(() => {
    root.render(<ThemeControl preference={preference} onChange={onChange} />);
  });
  return onChange;
}

const trigger = () => host.querySelector<HTMLButtonElement>(".theme-trigger");
const rows = () => [...document.querySelectorAll<HTMLButtonElement>(".theme-row")];
const popover = () => document.querySelector("#theme-popover");

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.useRealTimers();
});

describe("theme trigger", () => {
  it("is one button that names the choice and the dialog it opens", () => {
    render("dark");
    const button = trigger();
    expect(button?.tagName).toBe("BUTTON");
    expect(button?.getAttribute("aria-haspopup")).toBe("dialog");
    expect(button?.getAttribute("aria-label")).toContain("Theme");
    expect(button?.getAttribute("aria-label")).toContain("dark");
    expect(button?.getAttribute("aria-expanded")).toBe("false");
    expect(host.querySelector(".theme-tooltip")?.textContent).toBe("Theme");
  });

  it("shows the sun, the moon and the monitor per preference", () => {
    render("light");
    expect(trigger()?.querySelector("svg.lucide-sun")).not.toBeNull();
    act(() => root.unmount());
    host.remove();

    render("dark");
    expect(trigger()?.querySelector("svg.lucide-moon")).not.toBeNull();
    act(() => root.unmount());
    host.remove();

    render("system");
    expect(trigger()?.querySelector("svg.lucide-monitor")).not.toBeNull();
  });
});

describe("the popover", () => {
  it("lists three radios in a group named Theme, marks the active one and mounts one blob", () => {
    render("system");
    act(() => {
      trigger()?.dispatchEvent(keyboard("Enter"));
    });
    expect(popover()?.getAttribute("role")).toBe("dialog");
    expect(popover()?.getAttribute("aria-label")).toBe("Theme");
    expect(document.querySelector("[role='radiogroup']")?.getAttribute("aria-label")).toBe("Theme");
    expect(rows().map((row) => row.textContent)).toEqual(["Light", "Dark", "System"]);
    expect(rows().map((row) => row.querySelector("svg") !== null)).toEqual([true, true, true]);
    expect(rows().map((row) => row.getAttribute("aria-checked"))).toEqual(["false", "false", "true"]);
    expect(rows()[2].className).toContain("is-active");
    expect(rows()[2].tabIndex).toBe(0);
    expect(rows()[0].tabIndex).toBe(-1);
    const host0 = document.querySelector(".theme-rows .theme-popover-glass");
    expect(host0?.children.length).toBe(1);
    expect(host0?.querySelectorAll(".theme-blob").length).toBe(1);
  });

  it("opens on a keyboard press and closes on Escape with focus back on the trigger", () => {
    render("dark");
    act(() => {
      trigger()?.dispatchEvent(keyboard("Enter"));
    });
    expect(popover()).not.toBeNull();
    act(() => {
      document.dispatchEvent(keyboard("Escape"));
    });
    expect(popover()).toBeNull();
    expect(trigger()?.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement?.className ?? "").toContain("theme-trigger");
  });

  it("moves from the focused row with the arrows, Home and End", () => {
    render("light");
    act(() => {
      trigger()?.dispatchEvent(keyboard("ArrowDown"));
    });
    expect(document.activeElement?.className ?? "").toContain("theme-row");
    act(() => document.activeElement?.dispatchEvent(keyboard("ArrowDown")));
    expect(document.activeElement?.textContent).toBe("Dark");
    act(() => document.activeElement?.dispatchEvent(keyboard("Home")));
    expect(document.activeElement?.textContent).toBe("Light");
    act(() => document.activeElement?.dispatchEvent(keyboard("End")));
    expect(document.activeElement?.textContent).toBe("System");
    act(() => document.activeElement?.dispatchEvent(keyboard("ArrowRight")));
    expect(document.activeElement?.textContent).toBe("System");
    act(() => document.activeElement?.dispatchEvent(keyboard("ArrowUp")));
    expect(document.activeElement?.textContent).toBe("Dark");
  });

  it("chooses a row once and passes the trigger as the reveal group", () => {
    const onChange = render("light");
    act(() => {
      trigger()?.dispatchEvent(keyboard("Enter"));
    });
    act(() => {
      rows()[2].click();
    });
    expect(onChange).toHaveBeenCalledOnce();
    const [value, origin, group] = onChange.mock.calls[0] as [Preference, DOMRect, HTMLElement];
    expect(value).toBe("system");
    expect(typeof origin.left).toBe("number");
    // themeReveal adds `theme-switch-instant` to this element: it must be the trigger.
    expect(group).toBe(trigger());
    expect(popover()).toBeNull();
  });

  it("chooses with Space on a row, once, even when the browser also clicks it", () => {
    const onChange = render("light");
    act(() => {
      trigger()?.dispatchEvent(keyboard("Enter"));
    });
    const row = rows()[1];
    act(() => row.dispatchEvent(keyboard(" ")));
    expect(onChange).not.toHaveBeenCalled();
    act(() => {
      row.dispatchEvent(new KeyboardEvent("keyup", { key: " ", bubbles: true, cancelable: true }));
      row.dispatchEvent(new MouseEvent("click", { bubbles: true, detail: 0 }));
    });
    expect(onChange).toHaveBeenCalledOnce();
    expect(onChange.mock.calls[0][0]).toBe("dark");
    expect(popover()).toBeNull();
  });

  it("closes on an outside pointer press and on focus leaving the control", () => {
    render("dark");
    act(() => {
      trigger()?.dispatchEvent(keyboard("Enter"));
    });
    act(() => {
      document.body.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true }));
    });
    expect(popover()).toBeNull();

    act(() => {
      trigger()?.dispatchEvent(keyboard("Enter"));
    });
    const outside = document.createElement("button");
    document.body.appendChild(outside);
    act(() => {
      document.activeElement?.dispatchEvent(new FocusEvent("focusout", { bubbles: true, relatedTarget: outside }));
    });
    expect(popover()).toBeNull();
    outside.remove();
  });

  it("stays open through the grace and closes once it ends", () => {
    render("light");
    act(() => {
      trigger()?.dispatchEvent(keyboard("Enter"));
    });
    const root = host.querySelector<HTMLElement>(".theme-control")!;
    // The pointer leaves for good. jsdom reports the target as the body and not
    // the trigger, so React also reports a leave on the popover it wraps.
    act(() => setPointer(root, "pointerout", document.body));
    act(() => setPointer(root, "pointerleave", document.body));
    act(() => vi.advanceTimersByTime(399));
    expect(popover()).not.toBeNull();
    act(() => vi.advanceTimersByTime(1));
    expect(popover()).toBeNull();
  });

  it("does not close while the pointer is over the popover", () => {
    render("light");
    act(() => {
      trigger()?.dispatchEvent(keyboard("Enter"));
    });
    const root = host.querySelector<HTMLElement>(".theme-control")!;
    act(() => setPointer(root, "pointerleave", popover() as HTMLElement));
    act(() => vi.advanceTimersByTime(800));
    expect(popover()).not.toBeNull();
  });

  it("stays closed when a Tab passes the trigger", () => {
    render("light");
    act(() => {
      trigger()?.dispatchEvent(keyboard("Tab"));
    });
    expect(popover()).toBeNull();
  });
});

describe("reduced motion", () => {
  it("opens without the morph", () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query === "(prefers-reduced-motion: reduce)",
      media: query,
      addEventListener() {},
      removeEventListener() {},
      addListener() {},
      removeListener() {},
    }));
    render("light");
    act(() => {
      trigger()?.dispatchEvent(keyboard("Enter"));
    });
    expect(popover()?.className).toContain("is-instant");
    vi.unstubAllGlobals();
  });
});

function keyboard(key: string): KeyboardEvent {
  return new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true });
}
