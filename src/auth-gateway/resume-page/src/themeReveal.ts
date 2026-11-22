import { prefersReducedMotion } from './hooks/useReducedMotion'
import { persist, readPreference, resolve, type Preference } from './theme'
import './themeReveal.css'

type Commit = () => void

type ThemeViewTransition = {
  ready: Promise<void>
  finished: Promise<void>
  skipTransition: () => void
}

/** The rim is this wide, in CSS pixels, and does not grow with the circle. */
export const RIM_BAND = 36
/** feDisplacementMap offset is `scale * (channel - 0.5)`, so the scale is twice this cap. */
export const RIM_SHIFT = 12

let chain: Promise<void> = Promise.resolve()
let running = 0
let motion: Animation[] = []
let rimSvg: SVGSVGElement | null = null
let rimFrame = 0

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

function themeDurationMs(): number {
  const raw = getComputedStyle(document.documentElement).getPropertyValue('--dur-theme').trim()
  const value = Number.parseFloat(raw)
  return Number.isFinite(value) ? value : 700
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
    const refract = root.animate([{ filter: 'url(#theme-rim)' }, { filter: 'url(#theme-rim)' }], {
      duration,
      easing,
      fill: 'both',
      pseudoElement: '::view-transition-group(root)',
    })
    motion.push(clip, hold, refract)
    clips.push(
      clip.finished.catch(() => undefined),
      hold.finished.catch(() => undefined),
      refract.finished.catch(() => undefined),
    )
    startRim(clip, cx, cy, radius)
  }

  await new Promise<void>((done) => {
    const timer = setTimeout(() => {
      try {
        vt.skipTransition()
      } catch {
        // Already finished.
      }
      done()
    }, duration + 120)
    Promise.all([vt.finished.catch(() => undefined), ...clips]).then(() => {
      clearTimeout(timer)
      done()
    })
  })
}

function stopMotion(): void {
  for (const animation of motion) animation.cancel()
  motion = []
  if (rimFrame) cancelAnimationFrame(rimFrame)
  rimFrame = 0
  rimSvg?.remove()
  rimSvg = null
  const root = document.documentElement
  root.style.removeProperty('--theme-x')
  root.style.removeProperty('--theme-y')
  root.style.removeProperty('--theme-r')
  root.style.removeProperty('filter')
}

const SVG_NS = 'http://www.w3.org/2000/svg'

/**
 * Interior pixels stay the unfiltered snapshot. Displacement is masked to the
 * 36px band, then saturated, with a 1px specular line on the perimeter.
 */
function mountRim(width: number, height: number): SVGFEImageElement {
  const svg = document.createElementNS(SVG_NS, 'svg')
  svg.setAttribute('aria-hidden', 'true')
  svg.setAttribute('width', '0')
  svg.setAttribute('height', '0')
  svg.style.position = 'absolute'
  const filter = document.createElementNS(SVG_NS, 'filter')
  filter.id = 'theme-rim'
  filter.setAttribute('color-interpolation-filters', 'sRGB')
  filter.setAttribute('filterUnits', 'userSpaceOnUse')
  filter.setAttribute('x', '0')
  filter.setAttribute('y', '0')
  filter.setAttribute('width', String(width))
  filter.setAttribute('height', String(height))

  const map = document.createElementNS(SVG_NS, 'feImage')
  map.setAttribute('result', 'map')
  map.setAttribute('x', '0')
  map.setAttribute('y', '0')
  map.setAttribute('width', String(width))
  map.setAttribute('height', String(height))
  map.setAttribute('preserveAspectRatio', 'none')

  const shifted = document.createElementNS(SVG_NS, 'feDisplacementMap')
  shifted.setAttribute('in', 'SourceGraphic')
  shifted.setAttribute('in2', 'map')
  shifted.setAttribute('scale', String(RIM_SHIFT * 2))
  shifted.setAttribute('xChannelSelector', 'R')
  shifted.setAttribute('yChannelSelector', 'G')
  shifted.setAttribute('result', 'shifted')

  const band = document.createElementNS(SVG_NS, 'feComposite')
  band.setAttribute('in', 'shifted')
  band.setAttribute('in2', 'map')
  band.setAttribute('operator', 'in')
  band.setAttribute('result', 'band')

  const glass = document.createElementNS(SVG_NS, 'feColorMatrix')
  glass.setAttribute('in', 'band')
  glass.setAttribute('type', 'saturate')
  glass.setAttribute('values', '1.7')
  glass.setAttribute('result', 'glass')

  const hairMask = document.createElementNS(SVG_NS, 'feColorMatrix')
  hairMask.setAttribute('in', 'map')
  hairMask.setAttribute('type', 'matrix')
  hairMask.setAttribute('values', '0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 1 0 0')
  hairMask.setAttribute('result', 'hairMask')

  const paper = document.createElementNS(SVG_NS, 'feFlood')
  paper.setAttribute('flood-color', '#fffdf8')
  paper.setAttribute('flood-opacity', '0.85')
  paper.setAttribute('result', 'paper')

  const hair = document.createElementNS(SVG_NS, 'feComposite')
  hair.setAttribute('in', 'paper')
  hair.setAttribute('in2', 'hairMask')
  hair.setAttribute('operator', 'in')
  hair.setAttribute('result', 'hair')

  const withRim = document.createElementNS(SVG_NS, 'feComposite')
  withRim.setAttribute('in', 'glass')
  withRim.setAttribute('in2', 'SourceGraphic')
  withRim.setAttribute('operator', 'over')
  withRim.setAttribute('result', 'withRim')

  const out = document.createElementNS(SVG_NS, 'feComposite')
  out.setAttribute('in', 'hair')
  out.setAttribute('in2', 'withRim')
  out.setAttribute('operator', 'over')

  filter.append(map, shifted, band, glass, hairMask, paper, hair, withRim, out)
  svg.append(filter)
  document.body.append(svg)
  rimSvg = svg
  return map
}

function startRim(clip: Animation, cx: number, cy: number, radius: number): void {
  const width = Math.max(1, Math.round(window.innerWidth))
  const height = Math.max(1, Math.round(window.innerHeight))
  let map: SVGFEImageElement
  try {
    map = mountRim(width, height)
  } catch {
    rimSvg?.remove()
    rimSvg = null
    return
  }
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const buffer = ctx.createImageData(width, height)

  const frame = () => {
    if (!rimSvg) return
    const progress = clip.effect?.getComputedTiming().progress
    const t = typeof progress === 'number' ? progress : 0
    paintRimMap(buffer.data, width, height, cx, cy, t * radius)
    ctx.putImageData(buffer, 0, 0)
    const href = canvas.toDataURL()
    map.setAttribute('href', href)
    if (clip.playState === 'running' || clip.playState === 'paused') {
      rimFrame = requestAnimationFrame(frame)
    }
  }
  frame()
}

/** Neutral gray is no shift. Alpha marks the band. Blue marks the 1px perimeter. */
export function paintRimMap(
  data: Uint8ClampedArray,
  width: number,
  height: number,
  cx: number,
  cy: number,
  radius: number,
): void {
  data.fill(0)
  if (radius <= 0 || width <= 0 || height <= 0) return
  const inner = Math.max(0, radius - RIM_BAND)
  const y0 = Math.max(0, Math.floor(cy - radius))
  const y1 = Math.min(height - 1, Math.ceil(cy + radius))
  for (let y = y0; y <= y1; y++) {
    const dy = y + 0.5 - cy
    const dy2 = dy * dy
    if (dy2 > radius * radius) continue
    const outerDx = Math.sqrt(radius * radius - dy2)
    if (dy2 >= inner * inner) {
      paintSpan(data, width, y, cx, cy, cx - outerDx, cx + outerDx, radius, inner)
      continue
    }
    const innerDx = Math.sqrt(inner * inner - dy2)
    paintSpan(data, width, y, cx, cy, cx - outerDx, cx - innerDx, radius, inner)
    paintSpan(data, width, y, cx, cy, cx + innerDx, cx + outerDx, radius, inner)
  }
}

function paintSpan(
  data: Uint8ClampedArray,
  width: number,
  y: number,
  cx: number,
  cy: number,
  xStart: number,
  xEnd: number,
  radius: number,
  inner: number,
): void {
  const x0 = Math.max(0, Math.ceil(xStart))
  const x1 = Math.min(width - 1, Math.floor(xEnd))
  const span = Math.min(RIM_BAND, radius)
  if (span <= 0) return
  for (let x = x0; x <= x1; x++) {
    const dx = x + 0.5 - cx
    const dy = y + 0.5 - cy
    const dist = Math.hypot(dx, dy)
    if (dist < inner || dist > radius || dist < 1e-3) continue
    const strength = (dist - inner) / span
    const mag = strength * RIM_SHIFT
    const ux = dx / dist
    const uy = dy / dist
    const scale = RIM_SHIFT * 2
    const i = (y * width + x) * 4
    data[i] = channelByte(0.5 + (mag * ux) / scale)
    data[i + 1] = channelByte(0.5 + (mag * uy) / scale)
    data[i + 2] = radius - dist <= 1 ? 255 : 0
    data[i + 3] = 255
  }
}

function channelByte(channel: number): number {
  if (channel <= 0) return 0
  if (channel >= 1) return 255
  return Math.round(channel * 255)
}
