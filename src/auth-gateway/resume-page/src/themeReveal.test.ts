import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { persist } from './theme'
import { chooseTheme, durationMs, themeRevealIdle } from './themeReveal'

function rect(): DOMRect {
  return new DOMRect(8, 12, 180, 36)
}

function group(): HTMLDivElement {
  const el = document.createElement('div')
  document.body.appendChild(el)
  return el
}

function media(reduced: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: reduced && query === '(prefers-reduced-motion: reduce)',
    media: query,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  }))
}

function installTransition() {
  const start = vi.fn((update: () => void) => {
    update()
    return {
      ready: Promise.resolve(),
      finished: Promise.resolve(),
      updateCallbackDone: Promise.resolve(),
      skipTransition() {},
    }
  })
  Object.defineProperty(document, 'startViewTransition', {
    configurable: true,
    writable: true,
    value: start,
  })
  return start
}

beforeEach(() => {
  document.documentElement.style.setProperty('--dur-theme', '20ms')
})

afterEach(async () => {
  await themeRevealIdle()
  Reflect.deleteProperty(document, 'startViewTransition')
  document.documentElement.style.filter = ''
  document.documentElement.style.removeProperty('--dur-theme')
  Reflect.deleteProperty(document.documentElement, 'animate')
  vi.unstubAllGlobals()
})

describe('theme reveal skips', () => {
  it('does not play a circle when the resolved theme stays the same', async () => {
    media(false)
    persist('system')
    expect(document.documentElement.dataset.theme).toBe('dark')
    const start = installTransition()
    const commit = vi.fn()
    const host = group()

    chooseTheme('dark', rect(), host, commit)
    await themeRevealIdle()

    expect(start).not.toHaveBeenCalled()
    expect(commit).toHaveBeenCalledOnce()
    expect(document.cookie).toContain('theme.preference=dark')
    expect(localStorage.getItem('theme.preference')).toBeNull()
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(host.classList.contains('theme-switch-instant')).toBe(false)
  })

  it('does not play a circle under reduced motion', async () => {
    media(true)
    persist('dark')
    const start = installTransition()
    const commit = vi.fn()

    chooseTheme('light', rect(), group(), commit)
    await themeRevealIdle()

    expect(start).not.toHaveBeenCalled()
    expect(commit).toHaveBeenCalledOnce()
    expect(document.cookie).toContain('theme.preference=light')
    expect(localStorage.getItem('theme.preference')).toBeNull()
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(document.documentElement.style.colorScheme).toBe('light')
  })

  it('applies the theme in the same turn when the browser has no view transition', () => {
    media(false)
    persist('dark')
    const commit = vi.fn()

    chooseTheme('light', rect(), group(), commit)

    expect(commit).toHaveBeenCalledOnce()
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(document.cookie).toContain('theme.preference=light')
    expect(localStorage.getItem('theme.preference')).toBeNull()
  })

  it('plays one circle when a choice flips the resolved theme', async () => {
    media(false)
    persist('dark')
    const start = installTransition()

    chooseTheme('light', rect(), group(), () => {})
    await themeRevealIdle()

    expect(start).toHaveBeenCalledOnce()
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(document.cookie).toContain('theme.preference=light')
    expect(localStorage.getItem('theme.preference')).toBeNull()
  })

  it('holds a second choice until the running circle finishes', async () => {
    media(false)
    persist('dark')
    let finish = () => {}
    const finished = new Promise<void>((resolve) => {
      finish = resolve
    })
    const start = vi.fn((update: () => void) => {
      update()
      return {
        ready: Promise.resolve(),
        finished,
        updateCallbackDone: finished,
        skipTransition() {
          finish()
        },
      }
    })
    Object.defineProperty(document, 'startViewTransition', {
      configurable: true,
      writable: true,
      value: start,
    })

    chooseTheme('light', rect(), group(), () => {})
    chooseTheme('dark', rect(), group(), () => {})
    await vi.waitFor(() => expect(start).toHaveBeenCalledOnce())
    expect(document.documentElement.dataset.theme).toBe('light')

    finish()
    await themeRevealIdle()

    expect(start).toHaveBeenCalledTimes(2)
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(document.cookie).toContain('theme.preference=dark')
    expect(localStorage.getItem('theme.preference')).toBeNull()
  })
})

describe('theme duration', () => {
  it('reads a seconds token as milliseconds', () => {
    expect(durationMs('700ms')).toBe(700)
    expect(durationMs('.7s')).toBe(700)
    expect(durationMs('1ms')).toBe(1)
    expect(durationMs('0.7s')).toBe(700)
    expect(durationMs('1.5s')).toBe(1500)
  })

  it('answers NaN for a token it cannot read, so the caller keeps 700', () => {
    expect(Number.isFinite(durationMs(''))).toBe(false)
    expect(Number.isFinite(durationMs('fast'))).toBe(false)
  })

  it('does not cancel the transition before it can run', async () => {
    media(false)
    persist('dark')
    // A transition that ends on its own once its animations end, as the real one
    // does: `finished` stays pending until then, and `skipTransition` only ends
    // it early. A 20ms clip inside a 120ms watchdog must not trip the watchdog.
    let endTransition = () => {}
    const finished = new Promise<void>((resolve) => {
      endTransition = resolve
    })
    const skipTransition = vi.fn(() => endTransition())
    const start = vi.fn((update: () => void) => {
      update()
      return { ready: Promise.resolve(), finished, updateCallbackDone: finished, skipTransition }
    })
    Object.defineProperty(document, 'startViewTransition', {
      configurable: true,
      writable: true,
      value: start,
    })
    const clip = {
      finished: new Promise<void>((resolve) => {
        setTimeout(() => {
          resolve()
          endTransition()
        }, 20)
      }),
      cancel() {},
      playState: 'running',
      effect: { getComputedTiming: () => ({ progress: 0.5 }) },
    } as unknown as Animation
    Object.defineProperty(document.documentElement, 'animate', {
      configurable: true,
      value: () => clip,
    })

    chooseTheme('light', rect(), group(), () => {})
    await themeRevealIdle()

    expect(start).toHaveBeenCalledOnce()
    expect(skipTransition).not.toHaveBeenCalled()
    expect(document.documentElement.dataset.theme).toBe('light')
  })
})
