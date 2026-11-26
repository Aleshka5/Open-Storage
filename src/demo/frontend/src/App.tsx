import { useEffect, useState } from "react";
import { MapView } from "./MapView";
import { root } from "./map";
import { apply, persist, readPreference, type Preference } from "./theme";

const options = [
  { value: "light", label: "light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
] as const satisfies ReadonlyArray<{ value: Preference; label: string }>;

export function App() {
  const [preference, setPreference] = useState<Preference>(() => readPreference());

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
      <MapView root={root} />
    </div>
  );
}
