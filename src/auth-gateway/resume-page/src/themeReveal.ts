import { prefersReducedMotion } from './hooks/useReducedMotion'
import { persist, readPreference, resolve, type Preference } from './theme'
import './themeReveal.css'

type Commit = () => void

type ThemeViewTransition = {
  ready: Promise<void>
  finished: Promise<void>
  skipTransition: () => void
}

let chain: Promise<void> = Promise.resolve()
let running = 0
let motion: Animation[] = []

/** Resolves when a queued reveal has finished. Tests use this to settle the queue. */
export function themeRevealIdle(): Promise<void> {
  return chain
}

/**
 * Apply a user choice. A circle runs only when that choice flips the resolved
 * theme, the visitor allows motion, and the browser can start a view transition.
 * A second choice waits until the running circle finishes.
 */
export function chooseTheme(next: Preference, origin: DOMRect, group: HTMLElement, commit: Commit): void {
  if (running === 0 && !shouldAnimate(next)) {
    commit()
    persist(next)
    return
  }
  running += 1
  chain = chain
    .catch(() => undefined)
    .then(() => run(next, origin, group, commit))
    .finally(() => {
      running -= 1
    })
}

function shouldAnimate(next: Preference): boolean {
  if (resolve(readPreference()) === resolve(next)) return false
  if (prefersReducedMotion()) return false
  return typeof document.startViewTransition === 'function'
}

async function run(next: Preference, origin: DOMRect, group: HTMLElement, commit: Commit): Promise<void> {
  if (!shouldAnimate(next)) {
    commit()
    persist(next)
    return
  }

  group.classList.add('theme-switch-instant')
  let vt: ThemeViewTransition | undefined
  try {
    vt = document.startViewTransition(() => {
      commit()
      persist(next)
    })
    await vt.ready
    await playCircle(origin, vt)
  } catch {
    commit()
    persist(next)
    try {
      vt?.skipTransition()
    } catch {
      // The transition already finished.
    }
  } finally {
    group.classList.remove('theme-switch-instant')
    stopMotion()
  }
}

function cover(origin: DOMRect): { cx: number; cy: number; radius: number } {
  const cx = origin.left + origin.width / 2
  const cy = origin.top + origin.height / 2
  const radius = Math.hypot(Math.max(cx, window.innerWidth - cx), Math.max(cy, window.innerHeight - cy))
  return { cx, cy, radius }
}

/**
 * `--dur-theme` is authored as `700ms`, but the CSS minifier rewrites it to
 * `.7s`. `Number.parseFloat` alone therefore answers `0.7`, which the callers
 * read as 0.7 milliseconds: the circle finishes on its first frame and the
 * watchdog cancels the transition before `vt.ready` resolves. Parse the unit
 * instead of assuming milliseconds.
 */
export function durationMs(raw: string): number {
  const match = /^(-?\d*\.?\d+)(ms|s)?$/.exec(raw.trim())
  if (!match) return NaN
  const value = Number.parseFloat(match[1])
  if (!Number.isFinite(value)) return NaN
  return match[2] === 's' ? value * 1000 : value
}

function themeDurationMs(): number {
  const parsed = durationMs(getComputedStyle(document.documentElement).getPropertyValue('--dur-theme'))
  return Number.isFinite(parsed) ? parsed : 700
}

function themeEasing(): string {
  const raw = getComputedStyle(document.documentElement).getPropertyValue('--ease').trim()
  return raw || 'cubic-bezier(0.2, 0, 0, 1)'
}

/** Old layer stays opaque. The new layer’s circle is the only mask. */
async function playCircle(origin: DOMRect, vt: ThemeViewTransition): Promise<void> {
  const { cx, cy, radius } = cover(origin)
  const root = document.documentElement
  root.style.setProperty('--theme-x', `${cx}px`)
  root.style.setProperty('--theme-y', `${cy}px`)
  root.style.setProperty('--theme-r', `${radius}px`)

  const duration = themeDurationMs()
  const easing = themeEasing()
  const clips: Promise<unknown>[] = []
  if (typeof root.animate === 'function') {
    const clip = root.animate(
      [
        { clipPath: `circle(0px at ${cx}px ${cy}px)` },
        { clipPath: `circle(${radius}px at ${cx}px ${cy}px)` },
      ],
      { duration, easing, fill: 'both', pseudoElement: '::view-transition-new(root)' },
    )
    const hold = root.animate([{ opacity: 1 }, { opacity: 1 }], {
      duration,
      easing,
      fill: 'both',
      pseudoElement: '::view-transition-old(root)',
    })
    motion.push(clip, hold)
    clips.push(clip.finished.catch(() => undefined), hold.finished.catch(() => undefined))
  }

  // Order matters. The animations above hold the pseudo-elements open, so
  // `vt.finished` cannot resolve until they end; awaiting both at once deadlocks
  // and leaves the watchdog as the only exit. Wait for the circle first, then for
  // the transition to close, and let the watchdog cover a browser that aborts.
  const watchdog = setTimeout(() => {
    try {
      vt.skipTransition()
    } catch {
      // Already finished.
    }
  }, duration + 120)
  try {
    await Promise.all(clips)
    await vt.finished.catch(() => undefined)
  } finally {
    clearTimeout(watchdog)
  }
}

function stopMotion(): void {
  for (const animation of motion) animation.cancel()
  motion = []
  const root = document.documentElement
  root.style.removeProperty('--theme-x')
  root.style.removeProperty('--theme-y')
  root.style.removeProperty('--theme-r')
}
