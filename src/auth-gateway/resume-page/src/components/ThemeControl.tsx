import { lazy, Suspense, useLayoutEffect, useRef, useState } from 'react'
import type { Preference } from '../theme'
import './ThemeControl.css'

/** Off the initial chunk. The resume page's shell budget is 95 KB gzipped. */
const Glass = lazy(() => import('@samasante/liquid-glass').then((mod) => ({ default: mod.Glass })))

/** Frosted card. Bend, depth, and strength stay the package material defaults. */
const THUMB_OPTICS = { frost: 6, dispersion: 0.4 }

const options = [
  { value: 'light', label: 'light' },
  { value: 'dark', label: 'Dark' },
  { value: 'system', label: 'System' },
] as const satisfies ReadonlyArray<{ value: Preference; label: string }>

export function ThemeControl({
  preference,
  onChange,
}: {
  preference: Preference
  onChange: (next: Preference, origin: DOMRect, group: HTMLElement) => void
}) {
  const groupRef = useRef<HTMLDivElement>(null)
  const [box, setBox] = useState<{ x: number; w: number } | null>(null)
  const [seen, setSeen] = useState(preference)
  const [moving, setMoving] = useState(false)

  if (preference !== seen) {
    setSeen(preference)
    const instant = groupRef.current?.classList.contains('theme-switch-instant') ?? false
    setMoving(!instant)
  }

  useLayoutEffect(() => {
    const group = groupRef.current
    if (!group) return

    const place = () => {
      const selected = group.querySelector<HTMLElement>('.theme-segment:has(:checked)')
      if (!selected) return
      setBox({ x: selected.offsetLeft, w: selected.offsetWidth })
    }

    place()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(place)
    observer.observe(group)
    return () => observer.disconnect()
  }, [preference])

  return (
    <div
      ref={groupRef}
      className="theme-switch"
      role="radiogroup"
      aria-label="Theme"
      onTransitionEnd={(event) => {
        if (event.target !== event.currentTarget && !(event.target as HTMLElement).classList.contains('theme-thumb')) {
          return
        }
        if (event.propertyName === 'transform') setMoving(false)
      }}
    >
      {box ? (
        <Suspense
          fallback={
            <span
              className={moving ? 'theme-thumb is-moving' : 'theme-thumb'}
              style={{ transform: `translate3d(${box.x}px, 0, 0)`, width: box.w }}
              aria-hidden="true"
            />
          }
        >
          <Glass
            className={moving ? 'theme-thumb is-moving' : 'theme-thumb'}
            radius={0}
            optics={THUMB_OPTICS}
            style={{ transform: `translate3d(${box.x}px, 0, 0)`, width: box.w }}
            aria-hidden="true"
          >
            <span className="theme-thumb-face" />
          </Glass>
        </Suspense>
      ) : null}
      {options.map((option) => (
        <label key={option.value} className="theme-segment">
          <input
            type="radio"
            name="theme"
            value={option.value}
            checked={preference === option.value}
            onChange={() => {
              const origin = groupRef.current?.getBoundingClientRect()
              const group = groupRef.current
              if (!origin || !group) return
              onChange(option.value, origin, group)
            }}
          />
          {option.label}
        </label>
      ))}
    </div>
  )
}
