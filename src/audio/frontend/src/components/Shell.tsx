import { useEffect, useState } from 'react';
import { flushSync } from 'react-dom';
import { Outlet } from 'react-router-dom';
import { displayName, hubHref, signInHref } from '../hub';
import { probeAccess, type Gate } from '../session';
import { apply, readPreference, watchSystem, type Preference } from '../theme';
import { chooseTheme } from '../themeReveal';
import { ThemeControl } from './ThemeControl';

export function Shell() {
  const [gate, setGate] = useState<Gate>('checking');
  const [attempt, setAttempt] = useState(0);
  const [preference, setPreference] = useState<Preference>(() => readPreference());
  const [signingOut, setSigningOut] = useState(false);

  useEffect(() => {
    apply(readPreference());
    return watchSystem(() => apply(readPreference()));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setGate('checking');
    void probeAccess().then((next) => {
      if (!cancelled) setGate(next);
    });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  function onTheme(next: Preference, origin: DOMRect, group: HTMLElement) {
    chooseTheme(next, origin, group, () => {
      flushSync(() => setPreference(next));
    });
  }

  const signedIn = gate === 'ready' || gate === 'forbidden';
  const isGuest = gate === 'guest';

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
          <span aria-current="page">
            Audio
            {isGuest ? (
              <span className="service-lock" aria-hidden="true">
                🔒
              </span>
            ) : null}
          </span>
        </nav>
        <div className="header-right">
          <ThemeControl preference={preference} onChange={onTheme} />
          {gate === 'checking' ? <span className="muted">Checking sign-in…</span> : null}
          {gate === 'error' ? <span className="muted">Audio could not open this sign-in</span> : null}
          {isGuest ? (
            <a className="btn btn-small" href={signInHref()}>
              Sign in
            </a>
          ) : null}
          {signedIn ? (
            <>
              <span className="user-name">{displayName(undefined)}</span>
              <button
                type="button"
                className="btn btn-ghost btn-small"
                disabled={signingOut}
                onClick={() => {
                  setSigningOut(true);
                  window.location.assign(hubHref());
                }}
              >
                Sign out
              </button>
            </>
          ) : null}
        </div>
      </header>
      <main className="workspace" id="main">
        {gate === 'checking' ? <p className="muted gate-note">Checking sign-in…</p> : null}
        {gate === 'guest' ? (
          <div className="error-block">
            <p>Open this site through the hub. Audio does not handle sign-in.</p>
          </div>
        ) : null}
        {gate === 'forbidden' ? (
          <div className="error-block">
            <p>This account cannot use Audio.</p>
          </div>
        ) : null}
        {gate === 'error' ? (
          <div className="error-block">
            <p>Audio could not open this sign-in.</p>
            <button type="button" className="btn" onClick={() => setAttempt((value) => value + 1)}>
              Reload
            </button>
          </div>
        ) : null}
        {gate === 'ready' ? <Outlet /> : null}
      </main>
      <footer className="footer">
        <span>Filenkov · Audio</span>
        <span>Google sign-in · httpOnly cookies on .filenkov.store</span>
      </footer>
    </div>
  );
}
