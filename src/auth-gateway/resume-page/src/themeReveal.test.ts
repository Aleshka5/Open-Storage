import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { persist } from './theme'
import { chooseTheme, paintRimMap, RIM_BAND, RIM_SHIFT, themeRevealIdle } from './themeReveal'

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
    expect(localStorage.getItem('theme.preference')).toBe('dark')
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
    expect(localStorage.getItem('theme.preference')).toBe('light')
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
    expect(localStorage.getItem('theme.preference')).toBe('light')
  })

  it('plays one circle when a choice flips the resolved theme', async () => {
    media(false)
    persist('dark')
    const start = installTransition()

    chooseTheme('light', rect(), group(), () => {})
    await themeRevealIdle()

    expect(start).toHaveBeenCalledOnce()
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(localStorage.getItem('theme.preference')).toBe('light')
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
    expect(localStorage.getItem('theme.preference')).toBe('dark')
  })
})

describe('theme rim', () => {
  function shift(data: Uint8ClampedArray, width: number, x: number, y: number) {
    const i = (y * width + x) * 4
    const scale = RIM_SHIFT * 2
    const dx = scale * (data[i] / 255 - 0.5)
    const dy = scale * (data[i + 1] / 255 - 0.5)
    return { mag: Math.hypot(dx, dy), alpha: data[i + 3], hair: data[i + 2] }
  }

  it('displaces only a 36px band, by at most 12px, and leaves the interior alone', () => {
    const width = 160
    const height = 160
    const data = new Uint8ClampedArray(width * height * 4)
    const cx = 80
    const cy = 80
    const radius = 70
    paintRimMap(data, width, height, cx, cy, radius)

    expect(shift(data, width, cx, cy).alpha).toBe(0)
    expect(shift(data, width, cx + Math.round(radius - RIM_BAND - 3), cy).alpha).toBe(0)

    let edge = 0
    let inner = 0
    let samples = 0
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const dist = Math.hypot(x + 0.5 - cx, y + 0.5 - cy)
        const sample = shift(data, width, x, y)
        if (sample.alpha === 0) continue
        samples += 1
        expect(sample.mag).toBeLessThanOrEqual(RIM_SHIFT + 0.05)
        expect(dist).toBeGreaterThanOrEqual(radius - RIM_BAND - 0.75)
        expect(dist).toBeLessThanOrEqual(radius + 0.75)
        if (dist >= radius - 1.25) edge = Math.max(edge, sample.mag)
        if (dist <= radius - RIM_BAND + 2) inner = Math.max(inner, sample.mag)
        if (sample.hair > 0) expect(radius - dist).toBeLessThanOrEqual(1.25)
      }
    }
    expect(samples).toBeGreaterThan(0)
    expect(edge).toBeGreaterThan(RIM_SHIFT * 0.75)
    expect(inner).toBeLessThan(edge / 2)
  })

  it('removes the rim filter when the circle finishes', async () => {
    media(false)
    persist('dark')
    installTransition()
    const animate = vi.fn(
      () =>
        ({
          finished: Promise.resolve(),
          cancel() {},
          playState: 'finished',
          effect: { getComputedTiming: () => ({ progress: 1 }) },
        }) as unknown as Animation,
    )
    Object.defineProperty(document.documentElement, 'animate', {
      configurable: true,
      value: animate,
    })

    chooseTheme('light', rect(), group(), () => {})
    await themeRevealIdle()

    expect(animate).toHaveBeenCalled()
    expect(document.getElementById('theme-rim')).toBeNull()
    expect(document.body.querySelector('feDisplacementMap')).toBeNull()
    expect(document.documentElement.style.filter).toBe('')
  })
})
