import { useEffect } from 'react'

/**
 * Scroll-driven chrome (§7.2, §7.3).
 *
 * One passive, rAF-throttled `scroll` listener that NEVER calls setState. It
 * writes two things straight onto `<html>`:
 *
 *   data-header = 'top' | 'hidden' | 'condensed'
 *   data-owl    = 'hero' | 'docked'
 *
 * React re-rendering at 60 fps is the fastest way to lose the smoothness the
 * design document is about, so both are plain DOM writes.
 */

/** The owl docks once its hero slot has left the viewport. */
export const OWL_DOCK_AT = 180
/** ...and undocks lower down, so hovering the boundary does not flicker. */
export const OWL_UNDOCK_AT = 140

/**
 * The owl is a control only while it is docked. Reflecting that onto the button
 * here — rather than in React state — keeps the scroll path free of re-renders
 * while still hiding a dead control from assistive tech.
 */
function setOwlState(root: HTMLElement, state: 'hero' | 'docked'): void {
  if (root.dataset.owl === state) return
  root.dataset.owl = state
  const button = document.querySelector<HTMLButtonElement>('.owl')
  if (!button) return
  const hero = state === 'hero'
  button.setAttribute('aria-hidden', String(hero))
  button.tabIndex = hero ? -1 : 0
}

/** Frames smaller than this are trackpad noise, not intent. */
export const JITTER_FLOOR = 6
/** Accumulated travel in one direction before the header switches state. */
export const TRAVEL_THRESHOLD = 24
/** Below this the header is always 'top'. */
export const TOP_AT = 8
/** The header never hides this close to the top of the document. */
export const HIDE_BELOW = 96

function headerHasFocus(): boolean {
  const active = document.activeElement
  if (!active) return false
  const header = document.querySelector('.header')
  return header !== null && header.contains(active)
}

export function useScrollChrome(): void {
  useEffect(() => {
    const root = document.documentElement
    root.dataset.header = 'top'
    setOwlState(root, 'hero')

    let last = Math.max(0, window.scrollY)
    let acc = 0
    let frame = 0

    const apply = () => {
      frame = 0
      // iOS rubber-banding reports negative scrollY; clamping keeps the
      // state machine from toggling on an overscroll bounce.
      const y = Math.max(0, window.scrollY)

      // The owl answers an absolute-position question, so it is decided on every
      // frame; only the header reads direction and needs the jitter floor below.
      if (root.dataset.owl === 'docked') {
        if (y < OWL_UNDOCK_AT) setOwlState(root, 'hero')
      } else if (y > OWL_DOCK_AT) {
        setOwlState(root, 'docked')
      }

      if (y < TOP_AT) {
        root.dataset.header = 'top'
        last = y
        acc = 0
        return
      }
      // A keyboard user must never be tabbing into an off-screen header.
      if (headerHasFocus()) {
        root.dataset.header = 'condensed'
        last = y
        acc = 0
        return
      }

      const d = y - last
      // Trackpad micro-scrolls must not flip the header. Note `last` is only
      // advanced once a frame clears the floor, so a slow drift still adds up.
      if (Math.abs(d) < JITTER_FLOOR) return
      acc = Math.sign(d) === Math.sign(acc) ? acc + d : d
      last = y

      if (acc > TRAVEL_THRESHOLD && y > HIDE_BELOW) root.dataset.header = 'hidden'
      else if (acc < -TRAVEL_THRESHOLD) root.dataset.header = 'condensed'
    }

    const onScroll = () => {
      if (frame === 0) frame = requestAnimationFrame(apply)
    }

    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', onScroll)
      if (frame !== 0) cancelAnimationFrame(frame)
    }
  }, [])
}
