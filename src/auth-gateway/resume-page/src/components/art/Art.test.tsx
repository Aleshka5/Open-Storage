import { act, render, cleanup } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { Art } from './Art'

afterEach(() => {
  cleanup()
})

describe('Art', () => {
  it('puts every drawing on the page', () => {
    const { container } = render(<Art />)

    // Three moods, the tab icon, three clips, and the lander illustration.
    expect(container.querySelectorAll('.art-still')).toHaveLength(5)
    expect(container.querySelectorAll('.art-clip')).toHaveLength(3)
    expect(Array.from(container.querySelectorAll('.art-name')).map((n) => n.textContent)).toEqual([
      'Calm',
      'Angry',
      'Kind',
      'Tab icon',
      'calm-to-angry',
      'angry-to-calm',
      'calm-to-kind',
      'hero.png',
    ])
  })

  it('serves the clips from public/owl-clips as animateable SVGs', () => {
    const { container } = render(<Art />)
    for (const img of container.querySelectorAll('.art-clip')) {
      expect(img.getAttribute('src')).toMatch(/^\/owl-clips\/[a-z-]+\.svg$/)
    }
  })

  it('opens a drawing full-size and closes it again', async () => {
    const { container } = render(<Art />)
    const first = container.querySelector('.art-open') as HTMLButtonElement

    await act(async () => first.click())
    const overlay = container.querySelector('.art-overlay')
    expect(overlay).not.toBeNull()

    const close = overlay!.querySelector('button') as HTMLButtonElement
    await act(async () => close.click())
    expect(container.querySelector('.art-overlay')).toBeNull()
  })
})
