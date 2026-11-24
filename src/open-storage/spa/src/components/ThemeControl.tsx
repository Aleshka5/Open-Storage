import { Glass } from "@samasante/liquid-glass";
import { useLayoutEffect, useRef, useState } from "react";
import type { Preference } from "../theme";
import "./ThemeControl.css";

/** One rounded square. The labels sit under it so the rim refracts them. ADR-0006. */
const THUMB_RADIUS = 12;
const THUMB_OPTICS = {
  frost: 0,
  dispersion: 0.8,
  bend: 1,
  bendWidth: 0.9,
  depth: 1,
  curvature: 0.15,
  strength: 0.18,
  sheen: 0.45,
  sheenWidth: 4,
};

const options = [
  { value: "light", label: "light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
] as const satisfies ReadonlyArray<{ value: Preference; label: string }>;

export function ThemeControl({
  preference,
  onChange,
}: {
  preference: Preference;
  onChange: (next: Preference, origin: DOMRect, group: HTMLElement) => void;
}) {
  const groupRef = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<{ x: number; width: number; height: number } | null>(null);
  const [seen, setSeen] = useState(preference);
  const [moving, setMoving] = useState(false);

  if (preference !== seen) {
    setSeen(preference);
    const instant = groupRef.current?.classList.contains("theme-switch-instant") ?? false;
    setMoving(!instant);
  }

  useLayoutEffect(() => {
    const group = groupRef.current;
    if (!group) return;

    const place = () => {
      const selected = group.querySelector<HTMLElement>(".theme-segment:has(:checked)");
      if (!selected) return;
      setBox({ x: selected.offsetLeft, width: selected.offsetWidth, height: selected.offsetHeight });
    };

    place();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(place);
    observer.observe(group);
    return () => observer.disconnect();
  }, [preference]);

  return (
    <div
      ref={groupRef}
      className="theme-switch"
      role="radiogroup"
      aria-label="Theme"
      onTransitionEnd={(event) => {
        if (event.target !== event.currentTarget && !(event.target as HTMLElement).classList.contains("theme-thumb")) {
          return;
        }
        if (event.propertyName === "transform") setMoving(false);
      }}
    >
      {box ? (
        <Glass
          className={moving ? "theme-thumb is-moving" : "theme-thumb"}
          radius={THUMB_RADIUS}
          optics={THUMB_OPTICS}
          style={{ transform: `translate3d(${box.x}px, 0, 0)`, width: box.width, height: box.height }}
          aria-hidden="true"
        >
          <span className="theme-thumb-face" />
        </Glass>
      ) : null}
      {options.map((option) => (
        <label key={option.value} className="theme-segment">
          <input
            type="radio"
            name="theme"
            value={option.value}
            checked={preference === option.value}
            onChange={() => {
              const origin = groupRef.current?.getBoundingClientRect();
              const group = groupRef.current;
              if (!origin || !group) return;
              onChange(option.value, origin, group);
            }}
          />
          {option.label}
        </label>
      ))}
    </div>
  );
}
