import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth'
import { admin, errorResponse, jsonResponse, stranger } from '../test/fixtures'
import type { Session } from '../types'
import { Layout } from './Layout'

const FOCUSABLE = 'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'

beforeEach(() => {
  vi.stubGlobal('scrollTo', vi.fn())
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  setScrollY(0)
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

  it('shows Back to top only past 180px of scroll', async () => {
    const scrollTo = vi.fn()
    vi.stubGlobal('scrollTo', scrollTo)
    stubSession(stranger)
    renderLayout()
    await screen.findByText('Ann')
    expect(screen.queryByRole('button', { name: 'Back to top' })).not.toBeInTheDocument()

    act(() => {
      setScrollY(180)
      window.dispatchEvent(new Event('scroll'))
    })
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Back to top' })).not.toBeInTheDocument(),
    )

    act(() => {
      setScrollY(181)
      window.dispatchEvent(new Event('scroll'))
    })
    const button = await screen.findByRole('button', { name: 'Back to top' })
    await userEvent.click(button)
    expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: 'smooth' })
  })
})
