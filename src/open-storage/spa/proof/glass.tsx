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
    document.querySelector<HTMLButtonElement>(".theme-trigger")?.click();
    const clear = window.setTimeout(() => {
      document.querySelectorAll<HTMLElement>("[data-focus-ring]").forEach((node) => {
        delete node.dataset.focusRing;
      });
      if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    }, 60);
    return () => window.clearTimeout(clear);
  }, []);
  return (
    <>
      <div className="proof-scene" aria-hidden="true">
        {STRIPES.concat(STRIPES).map((color, index) => (
          <span key={index} className="proof-stripe" style={{ background: color }} />
        ))}
        <svg className="proof-mark proof-mark-trigger brand-mark" viewBox="0 0 32 32" aria-hidden="true">
          <path d="M16 3 L29 16 L16 29 L3 16 Z" fill="none" stroke="#1a1612" strokeWidth="1.75" />
          <circle cx="16" cy="16" r="3.2" fill="#b85c38" />
        </svg>
        <svg className="proof-mark proof-mark-blob brand-mark" viewBox="0 0 32 80" aria-hidden="true">
          <path d="M16 4 L28 16 L16 28 L4 16 Z" fill="none" stroke="#1a1612" strokeWidth="1.6" />
          <circle cx="16" cy="16" r="2.6" fill="#b85c38" />
          <path d="M16 48 L28 60 L16 72 L4 60 Z" fill="none" stroke="#1a1612" strokeWidth="1.6" />
          <circle cx="16" cy="60" r="2.6" fill="#b85c38" />
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
