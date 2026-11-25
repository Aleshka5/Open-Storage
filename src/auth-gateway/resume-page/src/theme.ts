/** Theme preference. The blocking script in `index.html` is the same contract, run before first paint. */

export const THEME_KEY = 'theme.preference'

export type Preference = 'light' | 'dark' | 'system'
export type ResolvedTheme = 'light' | 'dark'

function readCookie(name: string): string | null {
  const jar = document.cookie
  if (!jar) return null
  for (const part of jar.split(';')) {
    const trimmed = part.trim()
    const eq = trimmed.indexOf('=')
    if (eq === -1) continue
    if (trimmed.slice(0, eq) === name) return trimmed.slice(eq + 1)
  }
  return null
}

export function readPreference(): Preference {
  try {
    const stored = readCookie(THEME_KEY)
    if (stored === 'light' || stored === 'dark' || stored === 'system') return stored
  } catch {
    // A blocked cookie stays silent and paints dark.
  }
  return 'dark'
}

export function resolve(preference: string): ResolvedTheme {
  if (preference === 'light' || preference === 'dark') return preference
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

export function apply(preference: string): ResolvedTheme {
  const theme = resolve(preference)
  const root = document.documentElement
  root.dataset.theme = theme
  root.style.colorScheme = theme === 'light' ? 'light' : 'dark'
  const meta = document.querySelector('meta[name="color-scheme"]')
  if (meta) meta.setAttribute('content', root.style.colorScheme)
  return theme
}

/** Session cookie. `Domain` is shared only on filenkov.store. No expiry, so it dies with the browser. */
function themeCookieAttributes(): string {
  const parts = ['Path=/', 'SameSite=Lax']
  if (location.protocol === 'https:') parts.push('Secure')
  const host = location.hostname
  if (host === 'filenkov.store' || host.endsWith('.filenkov.store')) parts.push('Domain=.filenkov.store')
  return parts.join('; ')
}

/** Persist the choice, never the resolved theme. A write failure still paints. */
export function persist(preference: Preference): void {
  try {
    document.cookie = `${THEME_KEY}=${preference}; ${themeCookieAttributes()}`
  } catch {
    // Silent, same as a blocked read.
  }
  apply(preference)
}

/** `system` keeps listening. A fixed light or dark choice ignores the query. */
export function watchSystem(onChange: () => void): () => void {
  const media = window.matchMedia('(prefers-color-scheme: light)')
  const onScheme = () => {
    if (readPreference() === 'system') onChange()
  }
  media.addEventListener('change', onScheme)
  return () => media.removeEventListener('change', onScheme)
}

export const HUB_ORIGIN = 'https://filenkov.store'

/** On the hub origin the wordmark is an in-app navigation to `/`. */
export function brandStaysInApp(origin: string): boolean {
  return origin === HUB_ORIGIN
}
