import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  CIRCLE_RADIUS,
  MAX_STEP,
  WELL_INSET,
  blobGeometry,
  createBlobLoop,
  createSpring,
  geometryToFrame,
  mountThemeBlob,
  paintBlob,
  type Frame,
  type RowSet,
  type Tokens,
} from './themeBlob'

const HOST = { left: 100, top: 50, width: 200, height: 176 }
const TOKENS: Tokens = { radius: CIRCLE_RADIUS, rowInset: 6, stretch: 1.6 }
const ROWS: RowSet = {
  rows: [
    { x: 100, y: 50, height: 56 },
    { x: 100, y: 106, height: 56 },
    { x: 100, y: 162, height: 56 },
  ],
  active: 1,
}

const FRAME: Frame = { left: 10, top: 20, width: 40, height: 30, radius: 15 }

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('blob geometry', () => {
  it('is a 14px circle when no row is active', () => {
    const shape = blobGeometry(HOST, { rows: ROWS.rows, active: -1 }, { x: 150, y: 90 }, TOKENS)
    expect(shape.circle).toBe(true)
    if (!shape.circle) throw new Error('expected a circle')
    expect(shape.r).toBe(CIRCLE_RADIUS)
    expect(shape.cx).toBe(200)
    expect(shape.cy).toBe(138)
  })

  it('is a pill the row height minus 8 over a row', () => {
    const shape = blobGeometry(HOST, ROWS, null, TOKENS)
    expect(shape.circle).toBe(false)
    if (shape.circle) throw new Error('expected a pill')
    expect(shape.height).toBe(56 - 2 * WELL_INSET)
    expect(shape.radius).toBe(shape.height / 2)
    expect(shape.top).toBe(106 + WELL_INSET)
  })

  it('keeps the pill inside the host when the pointer is far to the right', () => {
    const shape = blobGeometry(HOST, ROWS, { x: 5000, y: 130 }, TOKENS)
    if (shape.circle) throw new Error('expected a pill')
    expect(shape.left).toBeGreaterThanOrEqual(HOST.left + TOKENS.rowInset)
    expect(shape.left + shape.width).toBeLessThanOrEqual(HOST.left + HOST.width - TOKENS.rowInset)
    expect(shape.width).toBeGreaterThan(0)
  })

  it('keeps the pill inside a narrow host by shrinking it', () => {
    const narrow = { left: 0, top: 0, width: 40, height: 80 }
    const shape = blobGeometry(narrow, { rows: [{ x: 0, y: 0, height: 56 }], active: 0 }, { x: 400, y: 20 }, TOKENS)
    if (shape.circle) throw new Error('expected a pill')
    expect(shape.left).toBe(6)
    expect(shape.width).toBeLessThanOrEqual(narrow.width - 12)
    expect(shape.left + shape.width).toBeLessThanOrEqual(narrow.width - 6)
  })

  it('moves the centre toward a pointer further from the row centre', () => {
    const centre = blobGeometry(HOST, ROWS, { x: 200, y: 130 }, TOKENS)
    const near = blobGeometry(HOST, ROWS, { x: 210, y: 130 }, TOKENS)
    const far = blobGeometry(HOST, ROWS, { x: 240, y: 130 }, TOKENS)
    if (centre.circle || near.circle || far.circle) throw new Error('expected pills')
    const cx = (s: typeof near) => s.left + s.width / 2
    expect(cx(near)).toBeGreaterThan(cx(centre))
    expect(cx(far)).toBeGreaterThan(cx(near))
    expect(far.width).toBeGreaterThan(near.width)
  })

  it('holds the circle inside the host with the inset', () => {
    const shape = blobGeometry(HOST, null, null, TOKENS)
    if (!shape.circle) throw new Error('expected a circle')
    expect(shape.cx - shape.r).toBeGreaterThanOrEqual(HOST.left + TOKENS.rowInset)
    expect(shape.cx + shape.r).toBeLessThanOrEqual(HOST.left + HOST.width - TOKENS.rowInset)
  })

  it('reaches a pill with no NaN for a zero-height host or row', () => {
    for (const host of [HOST, { left: 0, top: 0, width: 0, height: 0 }]) {
      for (const row of [ROWS, { rows: [{ x: 0, y: 0, height: 0 }], active: 0 }, null]) {
        const shape = blobGeometry(host, row, { x: 10, y: 10 }, TOKENS)
        const frame = geometryToFrame(shape)
        for (const value of Object.values(frame)) expect(Number.isFinite(value)).toBe(true)
      }
    }
  })
})

describe('blob spring', () => {
  const start: Frame = { left: 0, top: 0, width: 0, height: 0, radius: 0 }
  const target: Frame = { left: 120, top: 80, width: 60, height: 48, radius: 24 }
  it('converges on the target from an offset start', () => {
    const spring = createSpring(start)
    let frame = spring.current()
    let steps = 0
    while (!spring.settled(target) && steps < 400) {
      frame = spring.step(target)
      steps += 1
    }
    expect(steps).toBeLessThan(400)
    expect(Math.abs(frame.left - target.left)).toBeLessThanOrEqual(0.5)
    expect(Math.abs(frame.top - target.top)).toBeLessThanOrEqual(0.5)
    expect(Math.abs(frame.width - target.width)).toBeLessThanOrEqual(0.5)
    expect(Math.abs(frame.radius - target.radius)).toBeLessThanOrEqual(0.5)
    expect(spring.settled(target)).toBe(true)
  })

  it('never overshoots the target on any axis', () => {
    const spring = createSpring(start)
    const axes = ['left', 'top', 'width', 'height', 'radius'] as const
    let settled = false
    for (let i = 0; i < 100 && !settled; i += 1) {
      const before = spring.current()
      const frame = spring.step(target)
      for (const axis of axes) {
        // Bound: never past the target (zero overshoot), never more than
        // MAX_STEP of gap left unclosed, and never where the axis has not moved.
        expect(frame[axis] - target[axis]).toBeLessThanOrEqual(1e-9)
        expect(target[axis] - frame[axis]).toBeLessThanOrEqual(Math.max(MAX_STEP, Math.abs(before[axis] - target[axis])) + 1e-9)
      }
      settled = spring.settled(target)
    }
    expect(settled).toBe(true)
  })

  it('advances from a far start without overshooting either way', () => {
    const axes = ['left', 'top', 'width', 'height', 'radius'] as const
    // Signed distance left to travel before the target, measured from the
    // starting side: positive = still approaching, 0 = arrived, negative = past.
    const remaining = (frame: Frame, start: Frame, axis: (typeof axes)[number]) => {
      const fromAbove = start[axis] > target[axis];
      const onStartSide = fromAbove ? frame[axis] - target[axis] : target[axis] - frame[axis];
      // dir === 0 started on the target: report distance from it regardless of side.
      return Math.sign(start[axis] - target[axis]) === 0 ? Math.abs(onStartSide) : onStartSide;
    }
    for (const far of [
      { left: 3000, top: -2000, width: 1, height: 1, radius: 1 },
      { left: -2000, top: 3000, width: 900, height: 900, radius: 450 },
    ]) {
      const startFrame = { ...far }
      const initial = axes.map((axis) => remaining(startFrame, startFrame, axis))
      const spring = createSpring(startFrame)
      let settled = false
      for (let i = 0; i < 100 && !settled; i += 1) {
        const frame = spring.step(target)
        axes.forEach((axis, k) => {
          const now = remaining(frame, startFrame, axis)
          // Never past the target.
          expect(now).toBeGreaterThanOrEqual(-1e-9)
          if (initial[k] === 0) {
            expect(now).toBe(0)
            return
          }
          // Never further away than the start: the approach is monotone.
          expect(now).toBeLessThanOrEqual(initial[k] + 1e-9)
        })
        settled = spring.settled(target)
      }
      expect(settled).toBe(true)
      expect(spring.current()).toEqual(target)
    }
  })

  it('caps a single frame at 34px on every axis', () => {
    const far: Frame = { left: 2000, top: -2000, width: 3000, height: 3000, radius: 1500 }
    const spring = createSpring({ left: 0, top: 0, width: 0, height: 0, radius: 0 })
    const before = spring.current()
    const after = spring.step(far)
    for (const axis of ['left', 'top', 'width', 'height', 'radius'] as const) {
      expect(Math.abs(after[axis] - before[axis])).toBeLessThanOrEqual(MAX_STEP + 1e-9)
    }
  })

  it('places immediately with no velocity', () => {
    const spring = createSpring(start)
    spring.place(target)
    expect(spring.current()).toEqual(target)
    expect(spring.settled(target)).toBe(true)
  })
})

describe('blob loop', () => {
  const start: Frame = { left: 0, top: 0, width: 28, height: 28, radius: 14 }
  const target: Frame = { left: 90, top: 20, width: 60, height: 48, radius: 24 }

  function installRaf() {
    let next = 1
    const callbacks = new Map<number, FrameRequestCallback>()
    vi.stubGlobal('requestAnimationFrame', (fn: FrameRequestCallback) => {
      const id = next
      next += 1
      callbacks.set(id, fn)
      return id
    })
    vi.stubGlobal('cancelAnimationFrame', (id: number) => {
      callbacks.delete(id)
    })
    return {
      pending: () => callbacks.size,
      flush(times = 1) {
        for (let i = 0; i < times; i += 1) {
          const due = [...callbacks.entries()]
          callbacks.clear()
          for (const [, fn] of due) fn(performance.now())
        }
      },
    }
  }

  it('stops requesting frames once it has settled', () => {
    const raf = installRaf()
    const frames: Frame[] = []
    const loop = createBlobLoop((frame) => frames.push(frame))
    loop.start(start, target)
    expect(loop.running()).toBe(true)
    raf.flush(400)
    expect(loop.running()).toBe(false)
    expect(raf.pending()).toBe(0)
    expect(frames.at(-1)).toEqual(target)
    loop.dispose()
  })

  it('stops on dispose and never restarts', () => {
    const raf = installRaf()
    const paint = vi.fn()
    const loop = createBlobLoop(paint)
    loop.start(start, target)
    loop.dispose()
    expect(loop.running()).toBe(false)
    expect(raf.pending()).toBe(0)
    loop.start(start, target)
    expect(loop.running()).toBe(false)
  })

  it('places a frame without a loop', () => {
    const paint = vi.fn()
    const loop = createBlobLoop(paint)
    loop.place(target)
    expect(loop.running()).toBe(false)
    expect(paint).toHaveBeenLastCalledWith(target)
    loop.dispose()
  })

  it('writes the frame to the element style', () => {
    const element = document.createElement('span')
    paintBlob(element, FRAME)
    expect(element.style.left).toBe('10px')
    expect(element.style.top).toBe('20px')
    expect(element.style.width).toBe('40px')
    expect(element.style.height).toBe('30px')
    expect(element.style.borderRadius).toBe('15px')
  })
})

describe('blob mount', () => {
  function stage() {
    const host = document.createElement('div')
    host.className = 'theme-popover-glass'
    const list = document.createElement('div')
    const rows = [0, 1, 2].map((i) => {
      const row = document.createElement('button')
      row.className = 'theme-row'
      row.setAttribute('role', 'radio')
      const rect = { left: 100, top: 50 + i * 56, width: 184, height: 56, right: 284, bottom: 106 + i * 56, x: 100, y: 50 + i * 56, toJSON() {} }
      row.getBoundingClientRect = () => rect as DOMRect
      list.appendChild(row)
      return row
    })
    document.body.append(host, list)
    host.getBoundingClientRect = () =>
      ({ left: 100, top: 50, width: 184, height: 168, right: 284, bottom: 218, x: 100, y: 50, toJSON() {} }) as DOMRect
    return { host, list, rows }
  }

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('renders a .theme-blob with its glass children inside the host', () => {
    const { host, list } = stage()
    const mount = mountThemeBlob({ host, rows: list, active: () => 1, instant: true })
    const blob = host.querySelector('.theme-blob')
    expect(blob).not.toBeNull()
    expect(blob?.parentElement).toBe(host)
    expect(blob?.querySelector('.theme-blob-arc')).not.toBeNull()
    expect(blob?.querySelector('.theme-blob-sheen')).not.toBeNull()
    expect(blob?.getAttribute('aria-hidden')).toBe('true')
    mount.dispose()
    expect(host.querySelector('.theme-blob')).toBeNull()
  })

  it('places a pill over the active row without running a loop', () => {
    const { host, list } = stage()
    const mount = mountThemeBlob({ host, rows: list, active: () => 1, instant: true })
    const blob = host.querySelector<HTMLElement>('.theme-blob')!
    expect(blob.style.height).toBe('48px')
    expect(parseFloat(blob.style.top)).toBe(56 + 4)
    expect(parseFloat(blob.style.left)).toBeGreaterThanOrEqual(6)
    expect(parseFloat(blob.style.left) + parseFloat(blob.style.width)).toBeLessThanOrEqual(184 - 6)
    mount.dispose()
  })

  it('reports a circle when no row is active', () => {
    const { host, list } = stage()
    const mount = mountThemeBlob({ host, rows: list, active: () => -1, instant: true })
    const shape = mount.shape()
    expect(shape.circle).toBe(true)
    if (shape.circle) expect(shape.r).toBe(14)
    mount.dispose()
  })

  it('moves the painted geometry toward the pointer on sync', () => {
    const raf: Array<FrameRequestCallback> = []
    vi.stubGlobal('requestAnimationFrame', (fn: FrameRequestCallback) => {
      raf.push(fn)
      return raf.length
    })
    vi.stubGlobal('cancelAnimationFrame', () => {})
    const { host, list } = stage()
    let pointer = { x: 120, y: 130 }
    const mount = mountThemeBlob({ host, rows: list, active: () => 1, pointer: () => pointer })
    const blob = host.querySelector<HTMLElement>('.theme-blob')!
    const startLeft = parseFloat(blob.style.left)
    pointer = { x: 280, y: 130 }
    mount.sync()
    for (let i = 0; i < 60 && raf.length > 0; i += 1) {
      const due = raf.splice(0, raf.length)
      for (const fn of due) fn(0)
    }
    expect(parseFloat(blob.style.left) + parseFloat(blob.style.width) / 2).toBeGreaterThan(startLeft)
    mount.dispose()
  })
})
