import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  GRACE_DELAY,
  INTENT_DELAY,
  PopoverController,
  isOutsidePress,
  rowIndex,
  within,
} from './components/themePopover'

let controllers: PopoverController[] = []

function controller() {
  const c = new PopoverController()
  controllers.push(c)
  return c
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  for (const c of controllers) c.dispose()
  controllers = []
  vi.useRealTimers()
  document.body.innerHTML = ''
})

describe('theme popover constants', () => {
  it('holds the intent delay and the grace from the ADR', () => {
    expect(INTENT_DELAY).toBe(120)
    expect(GRACE_DELAY).toBe(400)
  })
})

describe('pointer state machine', () => {
  it('opens only after the intent delay', () => {
    const c = controller()
    expect(c.open).toBe(false)

    c.pointerEnter()
    vi.advanceTimersByTime(119)
    expect(c.open).toBe(false)

    vi.advanceTimersByTime(1)
    expect(c.open).toBe(true)
  })

  it('cancels the intent when the pointer leaves before it fires', () => {
    const c = controller()
    c.pointerEnter()
    vi.advanceTimersByTime(60)
    c.pointerLeave()
    vi.advanceTimersByTime(1000)
    expect(c.open).toBe(false)
  })

  it('closes only after the grace once the pointer leaves both', () => {
    const c = controller()
    c.pointerEnter()
    vi.advanceTimersByTime(120)
    expect(c.open).toBe(true)

    c.pointerLeave()
    vi.advanceTimersByTime(399)
    expect(c.open).toBe(true)

    vi.advanceTimersByTime(1)
    expect(c.open).toBe(false)
  })

  it('stays open when the pointer moves from the trigger to the popover', () => {
    const c = controller()
    c.pointerEnter()
    vi.advanceTimersByTime(120)
    c.pointerLeave()
    vi.advanceTimersByTime(200)
    c.pointerStay()
    vi.advanceTimersByTime(1000)
    expect(c.open).toBe(true)
  })

  it('cancels the grace when the pointer comes back', () => {
    const c = controller()
    c.pointerEnter()
    vi.advanceTimersByTime(120)
    c.pointerLeave()
    vi.advanceTimersByTime(399)
    c.pointerEnter()
    vi.advanceTimersByTime(1000)
    expect(c.open).toBe(true)
  })

  it('closes at once on Escape and on an outside press, with no grace', () => {
    const c = controller()
    c.requestOpen()
    c.closeNow()
    expect(c.open).toBe(false)

    c.requestOpen()
    c.pointerLeave()
    c.closeNow()
    vi.advanceTimersByTime(1000)
    expect(c.open).toBe(false)
  })

  it('leaves no timer behind after dispose', () => {
    const c = controller()
    c.pointerEnter()
    c.dispose()
    vi.advanceTimersByTime(1000)
    expect(c.open).toBe(false)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('tells every subscriber, and a removed one stops hearing', () => {
    const c = controller()
    const heard: boolean[] = []
    const off = c.subscribe(() => heard.push(c.open))
    c.requestOpen()
    c.closeNow()
    off()
    c.requestOpen()
    expect(heard).toEqual([true, false])
  })
})

describe('row navigation', () => {
  it('clamps at both ends and honours Home and End', () => {
    expect(rowIndex(0, { type: 'next' })).toBe(1)
    expect(rowIndex(2, { type: 'next' })).toBe(2)
    expect(rowIndex(0, { type: 'previous' })).toBe(0)
    expect(rowIndex(2, { type: 'previous' })).toBe(1)
    expect(rowIndex(1, { type: 'home' })).toBe(0)
    expect(rowIndex(1, { type: 'end' })).toBe(2)
    expect(rowIndex(-1, { type: 'next' })).toBe(0)
    expect(rowIndex(-1, { type: 'previous' })).toBe(0)
    expect(rowIndex(-1, { type: 'end' })).toBe(2)
    expect(rowIndex(0, { type: 'home' }, 0)).toBe(-1)
  })
})

describe('outside press', () => {
  it('is not fooled by a change of window focus, which carries no target', () => {
    const root = document.createElement('div')
    document.body.appendChild(root)
    const event = new FocusEvent('blur')
    expect(isOutsidePress(event, [root])).toBe(false)

    const inside = document.createElement('button')
    root.appendChild(inside)
    inside.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }))
    expect(isOutsidePress(new MouseEvent('pointerdown', { bubbles: true }), [document.body])).toBe(true)
    const insideEvent = { type: 'pointerdown', target: inside } as unknown as Event
    expect(isOutsidePress(insideEvent as PointerEvent, [root])).toBe(false)
    expect(isOutsidePress(new MouseEvent('pointerdown', { bubbles: true }), [root], document.body)).toBe(true)
    expect(within(null, root)).toBe(false)
  })
})

