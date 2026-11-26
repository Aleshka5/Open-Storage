import html from '../index.html?raw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { THEME_KEY, apply, persist, readPreference, resolve } from './theme'

function scheme(light: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: light && query === '(prefers-color-scheme: light)',
    media: query,
    onchange: null,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent() {
      return false
    },
  }))
}

function mockLocation(hostname: string, protocol: string) {
  vi.stubGlobal('location', { hostname, protocol })
}

function colorSchemeMeta(): HTMLMetaElement {
  const existing = document.querySelector('meta[name="color-scheme"]')
  if (existing instanceof HTMLMetaElement) return existing
  const meta = document.createElement('meta')
  meta.name = 'color-scheme'
  document.head.appendChild(meta)
  return meta
}

function cookieValue(): string | null {
  const prefix = `${THEME_KEY}=`
  for (const part of document.cookie.split(';')) {
    const entry = part.trim()
    if (entry.startsWith(prefix)) return entry.slice(prefix.length)
  }
  return null
}

function trackCookieWrites(): string[] {
  const writes: string[] = []
  const desc = Object.getOwnPropertyDescriptor(Document.prototype, 'cookie')
  if (!desc?.get || !desc.set) throw new Error('cookie descriptor missing')
  const get = desc.get
  const set = desc.set
  Object.defineProperty(document, 'cookie', {
    configurable: true,
    get() {
      return get.call(document)
    },
    set(value: string) {
      writes.push(String(value))
      set.call(document, value)
    },
  })
  return writes
}

function expectDarkPaint() {
  const meta = colorSchemeMeta()
  expect(readPreference()).toBe('dark')
  apply(readPreference())
  expect(document.documentElement.dataset.theme).toBe('dark')
  expect(document.documentElement.style.colorScheme).toBe('dark')
  expect(meta.getAttribute('content')).toBe('dark')
}

afterEach(() => {
  Reflect.deleteProperty(document, 'cookie')
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  document.querySelector('meta[name="color-scheme"]')?.remove()
})

describe('unknown theme.preference', () => {
  it('paints dark for a missing, unknown, empty, or thrown cookie even when the OS prefers light', () => {
    scheme(true)
    expect(THEME_KEY).toBe('theme.preference')

    window.localStorage.setItem(THEME_KEY, 'light')
    expect(cookieValue()).toBeNull()
    expectDarkPaint()

    document.cookie = `${THEME_KEY}=nope`
    expectDarkPaint()

    document.cookie = `${THEME_KEY}=`
    expectDarkPaint()

    Object.defineProperty(document, 'cookie', {
      configurable: true,
      get() {
        throw new Error('blocked')
      },
    })
    expectDarkPaint()
  })

  it('follows prefers-color-scheme when the preference is system', () => {
    document.cookie = `${THEME_KEY}=system`
    window.localStorage.setItem(THEME_KEY, 'dark')
    expect(readPreference()).toBe('system')

    const meta = colorSchemeMeta()
    scheme(true)
    expect(resolve('system')).toBe('light')
    apply('system')
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(document.documentElement.style.colorScheme).toBe('light')
    expect(meta.getAttribute('content')).toBe('light')

    scheme(false)
    expect(resolve('system')).toBe('dark')
    apply('system')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(document.documentElement.style.colorScheme).toBe('dark')
    expect(meta.getAttribute('content')).toBe('dark')
  })
})

describe('theme.preference cookie', () => {
  it('writes the session cookie and does not write localStorage', () => {
    const setItem = vi.spyOn(window.localStorage, 'setItem')
    const getItem = vi.spyOn(window.localStorage, 'getItem')
    window.localStorage.setItem(THEME_KEY, 'light')
    setItem.mockClear()
    getItem.mockClear()

    persist('dark')

    expect(cookieValue()).toBe('dark')
    expect(readPreference()).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(setItem).not.toHaveBeenCalled()
    expect(getItem).not.toHaveBeenCalled()
    expect(window.localStorage.getItem(THEME_KEY)).toBe('light')
  })

  it('still paints when the cookie write throws', () => {
    const setItem = vi.spyOn(window.localStorage, 'setItem')
    Object.defineProperty(document, 'cookie', {
      configurable: true,
      get() {
        return ''
      },
      set() {
        throw new Error('blocked')
      },
    })

    persist('light')

    expect(setItem).not.toHaveBeenCalled()
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(document.documentElement.style.colorScheme).toBe('light')
  })

  it('sets Domain=.filenkov.store on filenkov.store and storage.filenkov.store', () => {
    const writes = trackCookieWrites()
    const setItem = vi.spyOn(window.localStorage, 'setItem')

    for (const hostname of ['filenkov.store', 'storage.filenkov.store', 'rag.filenkov.store']) {
      writes.length = 0
      mockLocation(hostname, 'https:')
      persist('system')
      expect(writes).toEqual([
        `${THEME_KEY}=system; Path=/; SameSite=Lax; Secure; Domain=.filenkov.store`,
      ])
      expect(writes[0]).not.toMatch(/Max-Age|Expires|HttpOnly|Partitioned/i)
    }

    writes.length = 0
    mockLocation('filenkov.store', 'http:')
    persist('light')
    expect(writes).toEqual([`${THEME_KEY}=light; Path=/; SameSite=Lax; Domain=.filenkov.store`])

    writes.length = 0
    mockLocation('localhost', 'https:')
    persist('dark')
    expect(writes).toEqual([`${THEME_KEY}=dark; Path=/; SameSite=Lax; Secure`])
    expect(setItem).not.toHaveBeenCalled()
  })
})

describe('blocking script', () => {
  it('reads the cookie before first paint and does not touch localStorage', () => {
    const script = html.slice(html.indexOf('<script>'), html.indexOf('</script>'))
    expect(script).toContain("var KEY = 'theme.preference'")
    expect(script).toContain('document.cookie')
    expect(script).toContain("matchMedia('(prefers-color-scheme: light)')")
    expect(script).toContain('addEventListener')
    expect(script).not.toContain('localStorage')
    expect(script).not.toContain('type="module"')
  })
})
