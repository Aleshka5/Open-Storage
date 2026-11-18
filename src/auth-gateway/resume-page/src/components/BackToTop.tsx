import { useEffect, useState } from 'react'
import { prefersReducedMotion } from '../hooks/useReducedMotion'

/** The button appears once the article is worth scrolling back from. */
export const BACK_TO_TOP_AT = 180

/**
 * "Back to top" (§8, reduced to its one remaining job). The owl used to dock
 * here and change meaning on scroll; ADR-0006 removes the owl, so this is a
 * plain button with a single label and a single threshold.
 *
 * It is the only scroll-driven control that re-renders, and it flips a boolean
 * — not a frame — because a button that is not on screen must not be a tab
 * stop.
 */
export function BackToTop() {
  const [shown, setShown] = useState(false)

  useEffect(() => {
    let frame = 0

    const apply = () => {
      frame = 0
      setShown(Math.max(0, window.scrollY) > BACK_TO_TOP_AT)
    }

    const onScroll = () => {
      if (frame === 0) frame = requestAnimationFrame(apply)
    }

    apply()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', onScroll)
      if (frame !== 0) cancelAnimationFrame(frame)
    }
  }, [])

  if (!shown) return null

  const onClick = () => {
    const reduced = prefersReducedMotion()
    window.scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' })
    // Keyboard users land where the eye lands (§8.4, §11).
    document.getElementById('node-article')?.querySelector('h1')?.focus()
  }

  return (
    <button className="to-top" type="button" aria-label="Back to top" onClick={onClick}>
      <span aria-hidden="true">↑</span>
    </button>
  )
}
