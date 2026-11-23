/**
 * Dev-only page for looking at the theme lens over a high-frequency field.
 * Vite serves it; the production build input is index.html only.
 */
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { ThemeControl } from "../src/components/ThemeControl";
import "../src/index.css";
import { apply, type Preference } from "../src/theme";
import "./glass.css";

const STRIPES = ["#ff2d2d", "#ffd23a", "#2f6bff", "#19c37d", "#ff4fd8", "#35e0ff"];

function Proof() {
  const params = new URLSearchParams(window.location.search);
  const initial = params.get("theme") === "light" ? "light" : "dark";
  const [preference, setPreference] = useState<Preference>(initial);
  apply(preference);
  useEffect(() => {
    if (!params.has("open")) return;
    document.querySelector<HTMLButtonElement>(".theme-trigger")?.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Enter", bubbles: true }),
    );
  }, []);
  return (
    <>
      <div className="proof-scene" aria-hidden="true">
        {Array.from({ length: 96 }, (_, index) => (
          <span key={index} className="proof-stripe" style={{ background: STRIPES[index % STRIPES.length] }} />
        ))}
        <svg className="proof-mark brand-mark" viewBox="0 0 32 32">
          <path d="M16 3 L29 16 L16 29 L3 16 Z" fill="none" stroke="#1a1612" strokeWidth="1.75" />
          <circle cx="16" cy="16" r="3.2" fill="#b85c38" />
        </svg>
      </div>
      <header className="header">
        <a className="brand" href="#top">
          <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
            <path d="M16 3 L29 16 L16 29 L3 16 Z" fill="none" stroke="currentColor" strokeWidth="1.75" />
            <circle cx="16" cy="16" r="3.2" fill="var(--accent)" />
          </svg>
          <span className="brand-name">Filenkov</span>
        </a>
        <div className="header-right">
          <ThemeControl
            preference={preference}
            onChange={(next) => {
              apply(next);
              setPreference(next);
            }}
          />
        </div>
      </header>
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Proof />
  </StrictMode>,
);
