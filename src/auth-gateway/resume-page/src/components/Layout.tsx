import { useEffect, useState, type MouseEvent } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { loginPath } from '../api'
import { useAuth } from '../auth'
import { Owl } from './owl/Owl'
import { useScrollChrome } from '../hooks/useScrollChrome'
import { canUseService, isAdmin } from '../types'
import {
  HUB_ORIGIN,
  apply,
  brandStaysInApp,
  persist,
  readPreference,
  watchSystem,
  type Preference,
} from '../theme'

const themeOptions = [
  { value: 'light', label: 'light' },
  { value: 'dark', label: 'Dark' },
  { value: 'system', label: 'System' },
] as const satisfies ReadonlyArray<{ value: Preference; label: string }>

function Mark() {
  return (
    <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
      <path d="M16 3 L29 16 L16 29 L3 16 Z" fill="none" stroke="currentColor" strokeWidth="1.75" />
      <circle cx="16" cy="16" r="3.2" fill="var(--accent)" />
    </svg>
  )
}

/**
 * Service links (§7.1). A link is live when the session grants `family` or
 * `admin` on that service, or carries realm `admin`; otherwise it shows a lock
 * that leads into `/auth/login?return_to=<this path>`, which is a working
 * sign-in and the same destination the edge would pick. Image stays hidden
 * unless it is granted: the edge would answer `403`, and advertising a `403`
 * is noise.
 */
const services = [
  { label: 'Storage', href: 'https://storage.filenkov.store', service: 'storage' },
  { label: 'Hermes', href: 'https://hermes.filenkov.store', service: null },
  { label: 'RAG', href: 'https://rag.filenkov.store', service: 'rag' },
  { label: 'Image', href: 'https://image.filenkov.store', service: 'image' },
] as const

export function Layout() {
  const { user, loading, logout } = useAuth()
  const { pathname, search } = useLocation()
  const navigate = useNavigate()
  const [departing, setDeparting] = useState(false)
  const [preference, setPreference] = useState<Preference>(() => readPreference())
  const admin = isAdmin(user)
  const here = `${pathname}${search}`

  useScrollChrome()

  useEffect(() => {
    apply(readPreference())
    return watchSystem(() => apply(readPreference()))
  }, [])

  function onBrandClick(event: MouseEvent<HTMLAnchorElement>) {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.altKey ||
      event.ctrlKey ||
      event.shiftKey
    ) {
      return
    }
    if (!brandStaysInApp(window.location.origin)) return
    event.preventDefault()
    navigate('/')
  }

  function onTheme(next: Preference) {
    setPreference(next)
    persist(next)
  }

  async function onSignOut(event: MouseEvent<HTMLButtonElement>) {
    event.preventDefault()
    setDeparting(true)
    try {
      await logout()
    } finally {
      setDeparting(false)
    }
  }

  return (
    <div className="shell">
      <a className="skip-link" href="#node-article">
        Skip to article
      </a>
      <header className="header">
        <a className="brand" href={HUB_ORIGIN} onClick={onBrandClick}>
          <Mark />
          <span className="brand-name">Filenkov</span>
        </a>
        <nav className="service-nav" aria-label="Primary">
          {services.map((service) => {
            const allowed = service.service ? canUseService(user, service.service) : Boolean(user)
            if (service.service === 'image' && !allowed) return null
            const locked = !allowed
            const href = locked && !user ? loginPath(here) : service.href
            return (
              <a
                key={service.label}
                href={href}
                title={locked ? (user ? 'Access not granted' : 'Sign in required') : undefined}
              >
                {service.label}
                {locked ? (
                  <span className="service-lock" aria-hidden="true">
                    🔒
                  </span>
                ) : null}
              </a>
            )
          })}
          {admin ? <Link to="/admin">Admin</Link> : null}
        </nav>
        <div className="header-right">
          <div className="theme-switch" role="radiogroup" aria-label="Theme">
            {themeOptions.map((option) => (
              <label key={option.value} className="theme-segment">
                <input
                  type="radio"
                  name="theme"
                  value={option.value}
                  checked={preference === option.value}
                  onChange={() => onTheme(option.value)}
                />
                {option.label}
              </label>
            ))}
          </div>
          {loading ? (
            <span className="muted">Checking sign-in…</span>
          ) : user ? (
            <>
              <span className="user-name">{user.name}</span>
              <button
                type="button"
                className="btn btn-ghost btn-small"
                disabled={departing}
                onClick={onSignOut}
              >
                Sign out
              </button>
            </>
          ) : (
            <a className="btn btn-small" href={loginPath(here)}>
              Sign in
            </a>
          )}
        </div>
      </header>
      <main className="main" id="main">
        {/* The hero owl is the first thing in the flow, as it was before ADR-0006.
            Docked, the same component becomes the "Back to top" button. */}
        <Owl />
        <Outlet />
      </main>
      <footer className="footer">
        <span>Filenkov · personal tools</span>
        <span>Google sign-in · httpOnly cookies on .filenkov.store</span>
      </footer>
    </div>
  )
}
