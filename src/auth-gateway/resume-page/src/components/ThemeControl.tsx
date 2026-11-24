import { lazy, Suspense, useLayoutEffect, useRef, useState } from 'react'
import type { Preference } from '../theme'
import './ThemeControl.css'

/** Off the initial chunk. The resume page's shell budget is 95 KB gzipped. */
const Glass = lazy(() => import('@samasante/liquid-glass').then((mod) => ({ default: mod.Glass })))

/** One circle. The rim is thick enough to read on a flat header. ADR-0005. */
const THUMB_OPTICS = {
  frost: 8,
  dispersion: 0.7,
  bend: 0.85,
  bendWidth: 0.28,
  depth: 0.45,
  strength: 0.16,
  sheen: 0.9,
  sheenWidth: 8,
}

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
  const [box, setBox] = useState<{ x: number; size: number } | null>(null)
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
      const size = selected.offsetHeight
      setBox({ x: selected.offsetLeft + (selected.offsetWidth - size) / 2, size })
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
              style={{ transform: `translate3d(${box.x}px, 0, 0)`, width: box.size, height: box.size }}
              aria-hidden="true"
            />
          }
        >
          <Glass
            className={moving ? 'theme-thumb is-moving' : 'theme-thumb'}
            radius={999}
            optics={THUMB_OPTICS}
            style={{ transform: `translate3d(${box.x}px, 0, 0)`, width: box.size, height: box.size }}
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
