import { useEffect, useRef, useState, type ReactNode } from "react";
import { flushSync } from "react-dom";
import { NavLink, useLocation } from "react-router-dom";
import { apply, readPreference, watchSystem, type Preference } from "../theme";
import { chooseTheme } from "../themeReveal";
import { hubHref, signInHref } from "../utils/hub";
import { ThemeControl } from "./ThemeControl";

export function Layout({ children }: { children: ReactNode }) {
  const location = useLocation();
  const previousPath = useRef<string | null>(null);
  const [preference, setPreference] = useState<Preference>(() => readPreference());

  useEffect(() => {
    apply(readPreference());
    return watchSystem(() => apply(readPreference()));
  }, []);

  function onTheme(next: Preference, origin: DOMRect, group: HTMLElement) {
    chooseTheme(next, origin, group, () => {
      flushSync(() => setPreference(next));
    });
  }

  useEffect(() => {
    const main = document.getElementById("main");
    const heading = main?.querySelector("h1");
    const live = document.getElementById("route-announcer");
    if (live && heading) live.textContent = heading.textContent ?? "";
    const changed = previousPath.current !== null && previousPath.current !== location.pathname;
    previousPath.current = location.pathname;
    if (!(heading instanceof HTMLElement)) return;
    heading.tabIndex = -1;
    if (changed) heading.focus();
  }, [location.pathname]);

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="header">
        <a className="brand" href={hubHref()}>
          <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
            <path
              d="M16 3 L29 16 L16 29 L3 16 Z"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.75"
            />
            <circle cx="16" cy="16" r="3.2" fill="var(--accent)" />
          </svg>
          <span className="brand-name">Filenkov</span>
        </a>
        <nav className="service-nav" aria-label="Primary">
          <span aria-current="page">Documents</span>
        </nav>
        <nav className="service-nav" aria-label="Sections">
          <NavLink to="/files">Files</NavLink>
          <NavLink to="/chat">Chat</NavLink>
        </nav>
        <div className="header-right">
          <ThemeControl preference={preference} onChange={onTheme} />
          <a className="btn btn-small" href={signInHref()}>
            Sign in
          </a>
        </div>
      </header>
      <main className="main" id="main" tabIndex={-1}>
        {children}
      </main>
      <footer className="footer">
        <span>Filenkov · Documents</span>
        <span>Google sign-in · httpOnly cookies on .filenkov.store</span>
      </footer>
      <p id="route-announcer" className="sr-only" aria-live="polite" />
    </div>
  );
}
