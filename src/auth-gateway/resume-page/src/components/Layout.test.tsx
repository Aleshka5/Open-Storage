import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth'
import { admin, errorResponse, jsonResponse, stranger } from '../test/fixtures'
import type { Session } from '../types'
import * as theme from '../theme'
import { Layout } from './Layout'

const FOCUSABLE = 'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'

beforeEach(() => {
  vi.stubGlobal('scrollTo', vi.fn())
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  setScrollY(0)
  // jsdom keeps <html> between tests; a leftover 'docked' would leak into the next one.
  delete document.documentElement.dataset.owl
})

function setScrollY(y: number) {
  Object.defineProperty(window, 'scrollY', { value: y, configurable: true, writable: true })
}

function renderLayout(path = '/') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<div>outlet</div>} />
            <Route path="/auth" element={<div>auth-outlet</div>} />
            <Route path="/admin" element={<div>admin-outlet</div>} />
            <Route path="*" element={<div>node-outlet</div>} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

/** `/auth/session` returns `session` (or 401); `/auth/logout` succeeds. */
function stubSession(session: Session | null) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    if (url === '/auth/session') {
      return session ? jsonResponse(session) : errorResponse('unauthorized', 401)
    }
    if (url === '/auth/logout' && method === 'POST') return jsonResponse({ status: 'ok' })
    return errorResponse(`unexpected ${url}`, 500)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('Layout', () => {
  it('offers sign-in and locked service links to a guest', async () => {
    const fetchMock = stubSession(null)
    renderLayout()
    const signIn = await screen.findByRole('link', { name: 'Sign in' })
    expect(signIn).toHaveAttribute('href', '/auth/login?return_to=%2F')

    for (const [label, href] of [
      ['Storage', 'https://storage.filenkov.store'],
      ['Hermes', 'https://hermes.filenkov.store'],
      ['RAG', 'https://rag.filenkov.store'],
    ]) {
      const link = screen.getByRole('link', { name: new RegExp(`^${label}`) })
      expect(link).toHaveAttribute('title', 'Sign in required')
      expect(link).toHaveAttribute('href', '/auth/login?return_to=%2F')
      expect(link.querySelector('.service-lock')).not.toBeNull()
      expect(href).toContain('filenkov.store')
    }

    expect(screen.queryByRole('link', { name: 'Admin' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /^Image/ })).not.toBeInTheDocument()
    expect(fetchMock.mock.calls.map((call) => String(call[0]))).toEqual(['/auth/session'])
  })

  it('keeps the return path of the page the reader is on', async () => {
    stubSession(null)
    renderLayout('/experience/sber')
    const signIn = await screen.findByRole('link', { name: 'Sign in' })
    expect(signIn).toHaveAttribute('href', '/auth/login?return_to=%2Fexperience%2Fsber')
    expect(screen.getByRole('link', { name: /^Storage/ })).toHaveAttribute(
      'href',
      '/auth/login?return_to=%2Fexperience%2Fsber',
    )
  })

  it('shows the name, Admin and every unlocked service to a realm admin', async () => {
    stubSession(admin)
    renderLayout()
    expect(await screen.findByText('Boss')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Admin' })).toHaveAttribute('href', '/admin')
    expect(screen.getByRole('link', { name: 'Image' })).toHaveAttribute(
      'href',
      'https://image.filenkov.store',
    )
    expect(document.querySelectorAll('.service-lock')).toHaveLength(0)
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument()
  })

  it('unlocks what the session grants and locks what it does not', async () => {
    stubSession(stranger)
    renderLayout()
    expect(await screen.findByText('Ann')).toBeInTheDocument()

    // family on storage, so live and plain.
    const storage = screen.getByRole('link', { name: 'Storage' })
    expect(storage).toHaveAttribute('href', 'https://storage.filenkov.store')
    expect(storage).not.toHaveAttribute('title')

    // no level on rag: still shown, locked, and pointing at the service.
    const rag = screen.getByRole('link', { name: /^RAG/ })
    expect(rag).toHaveAttribute('title', 'Access not granted')
    expect(rag).toHaveAttribute('href', 'https://rag.filenkov.store')

    // signed in is enough for Hermes, which has no per-service roles.
    expect(screen.getByRole('link', { name: 'Hermes' })).not.toHaveAttribute('title')

    expect(screen.queryByRole('link', { name: 'Admin' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /^Image/ })).not.toBeInTheDocument()
  })

  it('shows Image to a reader with family on it', async () => {
    const person: Session = {
      ...stranger,
      services: stranger.services.map((row) =>
        row.service === 'image' ? { ...row, level: 'family' as const } : row,
      ),
    }
    stubSession(person)
    renderLayout()
    expect(await screen.findByText('Ann')).toBeInTheDocument()
    const image = screen.getByRole('link', { name: 'Image' })
    expect(image).toHaveAttribute('href', 'https://image.filenkov.store')
    expect(image).not.toHaveAttribute('title')
  })

  it('signs out with POST /auth/logout and a requested-with header', async () => {
    const fetchMock = stubSession(stranger)
    renderLayout()
    expect(await screen.findByText('Ann')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))

    await waitFor(() => {
      const post = fetchMock.mock.calls.find(
        ([url, init]) => String(url) === '/auth/logout' && init?.method === 'POST',
      )
      expect(post).toBeTruthy()
      expect(post?.[1]?.headers).toMatchObject({ 'X-Requested-With': 'XMLHttpRequest' })
    })
    expect(await screen.findByRole('link', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.queryByText('Ann')).not.toBeInTheDocument()
  })

  it('puts the skip link first in the tab order, pointing at the article', async () => {
    stubSession(stranger)
    const { container } = renderLayout()
    await screen.findByText('Ann')
    const first = container.querySelector(FOCUSABLE)
    expect(first).toHaveClass('skip-link')
    expect(first).toHaveAttribute('href', '#node-article')
  })

  it('shows the docked owl only past 180px of scroll, and it goes back to the top', async () => {
    const scrollTo = vi.fn()
    vi.stubGlobal('scrollTo', scrollTo)
    stubSession(stranger)
    renderLayout()
    await screen.findByText('Ann')
    // The button exists at all times; at the top it is the hero, not a control.
    await waitFor(() => expect(document.documentElement.dataset.owl).toBe('hero'))
    const heroButton = document.querySelector<HTMLButtonElement>('.owl')!
    expect(heroButton.tabIndex).toBe(-1)
    expect(heroButton.getAttribute('aria-hidden')).toBe('true')

    act(() => {
      setScrollY(180)
      window.dispatchEvent(new Event('scroll'))
    })
    await waitFor(() => expect(document.documentElement.dataset.owl).toBe('hero'))

    act(() => {
      setScrollY(181)
      window.dispatchEvent(new Event('scroll'))
    })
    await waitFor(() => expect(document.documentElement.dataset.owl).toBe('docked'))
    const button = screen.getByRole('button', { name: 'Back to top' })
    expect(button).toHaveAttribute('aria-hidden', 'false')
    await userEvent.click(button)
    expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: 'smooth' })
  })

  it('names the theme control and keeps the three labels', async () => {
    stubSession(null)
    renderLayout()
    const group = await screen.findByRole('radiogroup', { name: 'Theme' })
    const light = screen.getByRole('radio', { name: 'light' })
    const dark = screen.getByRole('radio', { name: 'Dark' })
    const system = screen.getByRole('radio', { name: 'System' })
    expect(group).toContainElement(light)
    expect(group).toContainElement(dark)
    expect(group).toContainElement(system)
    expect(group.querySelector('.theme-thumb')).not.toBeNull()
    expect(dark).toBeChecked()

    await userEvent.click(light)
    expect(light).toBeChecked()
    expect(localStorage.getItem('theme.preference')).toBe('light')
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(document.documentElement.style.colorScheme).toBe('light')

    light.focus()
    await userEvent.keyboard('{ArrowRight}')
    expect(dark).toBeChecked()
    await userEvent.keyboard('{ArrowRight}')
    expect(system).toBeChecked()
    expect(localStorage.getItem('theme.preference')).toBe('system')
    expect(document.documentElement.dataset.theme).not.toBe('system')
  })

  it('points the wordmark at the hub and stays in the app on that origin', async () => {
    stubSession(null)
    const stays = vi.spyOn(theme, 'brandStaysInApp').mockReturnValue(true)
    renderLayout('/experience/sber')
    const brand = await screen.findByRole('link', { name: 'Filenkov' })
    expect(brand).toHaveAttribute('href', 'https://filenkov.store')
    await userEvent.click(brand)
    expect(stays).toHaveBeenCalled()
    expect(screen.getByText('outlet')).toBeInTheDocument()
  })
})
