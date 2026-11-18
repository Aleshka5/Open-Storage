import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { loginPath } from '../api'
import { useAuth } from '../auth'

const hubHost = 'filenkov.store'

function isLoopback(hostname: string): boolean {
  return hostname === 'localhost' || hostname === '127.0.0.1'
}

/**
 * Where the reader came from. Same-origin paths, https on filenkov.store, or
 * loopback in local dev. Anything else is dropped, so `return_to` cannot turn
 * the button into an open redirect.
 */
export function continueTarget(raw: string | null, pageOrigin = window.location.origin): string | null {
  if (!raw) return null
  let page: URL
  let dest: URL
  try {
    page = new URL(pageOrigin)
    dest = new URL(raw, pageOrigin)
  } catch {
    return null
  }
  if (dest.username || dest.password) return null
  if (dest.origin === page.origin) {
    return `${dest.pathname}${dest.search}${dest.hash}` || '/'
  }
  const host = dest.hostname.toLowerCase()
  if (isLoopback(host) && isLoopback(page.hostname) && (dest.protocol === 'http:' || dest.protocol === 'https:')) {
    return dest.href
  }
  if (dest.protocol !== 'https:') return null
  if (host !== hubHost && !host.endsWith(`.${hubHost}`)) return null
  return dest.href
}

/** `/auth` is one button. The gateway owns the Google exchange; the page only points at it. */
export const SIGN_IN_LABEL = 'Continue with Google'

function GoogleMark() {
  return (
    <svg className="google-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        d="M21.35 11.1h-9.18v2.96h5.27c-.23 1.22-1.37 3.58-5.27 3.58-3.17 0-5.76-2.62-5.76-5.84s2.59-5.84 5.76-5.84c1.8 0 3.01.77 3.7 1.43l2.52-2.43C16.54 3.54 14.5 2.6 12.17 2.6 7.03 2.6 2.87 6.76 2.87 11.9s4.16 9.3 9.3 9.3c5.37 0 8.92-3.77 8.92-9.08 0-.61-.07-1.07-.16-1.52Z"
      />
    </svg>
  )
}

export function Auth() {
  const { user, loading } = useAuth()
  const [params] = useSearchParams()
  const { pathname, search } = useLocation()
  const requested = continueTarget(params.get('return_to'))
  // On `/auth` itself the current path is the page, not a destination.
  const target = requested ?? (pathname === '/auth' ? '/' : `${pathname}${search}`)

  return (
    <section className="auth-page">
      <div className="panel stack">
        <p className="kicker">Sign in</p>
        <h1 style={{ fontSize: '2.1rem' }}>Google only.</h1>
        <p className="muted">
          This hub does not keep passwords. Continue with the Google account you want on Filenkov
          services. Sign-in sets httpOnly cookies — the page never sees a token.
        </p>
        {loading ? (
          <p className="muted">Checking sign-in…</p>
        ) : user ? (
          <>
            <p>
              Signed in as <strong>{user.name}</strong>.
            </p>
            <Link className="btn btn-ghost" to="/">
              Back home
            </Link>
          </>
        ) : (
          <a className="btn" href={loginPath(target)}>
            <GoogleMark />
            {SIGN_IN_LABEL}
          </a>
        )}
      </div>
    </section>
  )
}
