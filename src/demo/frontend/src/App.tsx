import { useEffect, useState } from "react";
import { DiagramView } from "./DiagramView";
import { MapView } from "./MapView";
import { root } from "./map";
import { apply, persist, readPreference, type Preference } from "./theme";
import "./diagram.css";

type Show = "map" | "diagram";

const SHOW_KEY = "demo.map.show";

function readShow(): Show {
  try {
    return window.localStorage.getItem(SHOW_KEY) === "diagram" ? "diagram" : "map";
  } catch {
    return "map";
  }
}

const options = [
  { value: "light", label: "light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
] as const satisfies ReadonlyArray<{ value: Preference; label: string }>;

export function App() {
  const [preference, setPreference] = useState<Preference>(() => readPreference());
  const [show, setShow] = useState<Show>(() => readShow());

  function chooseShow(next: Show) {
    setShow(next);
    try {
      window.localStorage.setItem(SHOW_KEY, next);
    } catch {
      // The switch still works for this visit when storage is blocked.
    }
  }

  useEffect(() => {
    apply(preference);
    if (preference !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: light)");
    const onChange = () => apply("system");
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [preference]);

  return (
    <div className="page">
      <header className="bar">
        <div className="brand">
          <a className="word" href="https://filenkov.store">
            filenkov
          </a>
          <span className="service">Map</span>
        </div>
        <div className="os-demo-show" role="radiogroup" aria-label="Show">
          <button
            type="button"
            className={show === "map" ? "os-demo-show__option os-demo-show__option--on" : "os-demo-show__option"}
            aria-pressed={show === "map"}
            onClick={() => chooseShow("map")}
          >
            Map
          </button>
          <button
            type="button"
            className={show === "diagram" ? "os-demo-show__option os-demo-show__option--on" : "os-demo-show__option"}
            aria-pressed={show === "diagram"}
            onClick={() => chooseShow("diagram")}
          >
            Diagram
          </button>
        </div>
        <div className="theme" role="radiogroup" aria-label="Theme">
          {options.map((option) => (
            <label key={option.value} className={preference === option.value ? "segment on" : "segment"}>
              <input
                type="radio"
                name="theme"
                value={option.value}
                checked={preference === option.value}
                onChange={() => {
                  setPreference(option.value);
                  persist(option.value);
                }}
              />
              {option.label}
            </label>
          ))}
        </div>
      </header>
      {show === "diagram" ? <DiagramView root={root} /> : <MapView root={root} />}
    </div>
  );
}
