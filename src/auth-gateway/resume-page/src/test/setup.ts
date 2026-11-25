import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

if (typeof ResizeObserver === 'undefined') {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  globalThis.ResizeObserver = ResizeObserverStub as typeof ResizeObserver
}

if (typeof window.matchMedia !== 'function') {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener() {},
      removeListener() {},
      addEventListener() {},
      removeEventListener() {},
      dispatchEvent() {
        return false
      },
    }) as MediaQueryList
}

/** Drop a host-only cookie and the shared `.filenkov.store` cookie. */
function clearThemeCookie() {
  document.cookie = 'theme.preference=; Path=/; Max-Age=0'
  const dom = (globalThis as { jsdom?: { reconfigure(settings: { url: string }): void } }).jsdom
  if (!dom) return
  dom.reconfigure({ url: 'https://filenkov.store/' })
  document.cookie = 'theme.preference=; Path=/; Domain=.filenkov.store; Max-Age=0'
  dom.reconfigure({ url: 'http://localhost:3000/' })
  document.cookie = 'theme.preference=; Path=/; Max-Age=0'
}

afterEach(() => {
  cleanup()
  localStorage.clear()
  clearThemeCookie()
  document.documentElement.removeAttribute('data-theme')
  document.documentElement.style.colorScheme = ''
})
