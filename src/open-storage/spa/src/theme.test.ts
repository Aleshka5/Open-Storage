import { afterEach, describe, expect, it, vi } from 'vitest'
import { THEME_KEY, apply, readPreference, resolve } from './theme'

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

function colorSchemeMeta(): HTMLMetaElement {
  const existing = document.querySelector('meta[name="color-scheme"]')
  if (existing instanceof HTMLMetaElement) return existing
  const meta = document.createElement('meta')
  meta.name = 'color-scheme'
  document.head.appendChild(meta)
  return meta
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
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  document.querySelector('meta[name="color-scheme"]')?.remove()
})

describe('unknown theme.preference', () => {
  it('paints dark for an unknown, empty, or thrown store even when the OS prefers light', () => {
    scheme(true)
    expect(THEME_KEY).toBe('theme.preference')

    localStorage.setItem(THEME_KEY, 'nope')
    expectDarkPaint()

    localStorage.setItem(THEME_KEY, '')
    expectDarkPaint()

    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    expectDarkPaint()
  })

  it('follows prefers-color-scheme when the preference is system', () => {
    localStorage.setItem(THEME_KEY, 'system')
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
