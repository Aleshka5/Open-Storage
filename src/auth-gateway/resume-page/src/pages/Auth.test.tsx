import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth'
import { admin, errorResponse, jsonResponse, stranger } from '../test/fixtures'
import { Auth, continueTarget } from './Auth'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

function renderAuth(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route path="/auth" element={<Auth />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

function stubSession(session: unknown, status = 200) {
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url === '/auth/session') {
      return status === 200 ? jsonResponse(session) : errorResponse('unauthorized', status)
    }
    return errorResponse('unexpected', 500)
  })
  vi.stubGlobal('fetch', fetch)
  return fetch
}

describe('continueTarget', () => {
  const origin = 'https://filenkov.store'

  it('keeps a same-origin path', () => {
    expect(continueTarget('/experience/sber?x=1', origin)).toBe('/experience/sber?x=1')
  })

  it('allows another https Filenkov host', () => {
    expect(continueTarget('https://storage.filenkov.store/app', origin)).toBe(
      'https://storage.filenkov.store/app',
    )
  })

  it('rejects a host outside the cookie domain', () => {
    expect(continueTarget('https://evil.example/phish', origin)).toBeNull()
    expect(continueTarget('https://filenkov.store.evil.example/', origin)).toBeNull()
    expect(continueTarget(null, origin)).toBeNull()
  })
})

describe('Auth', () => {
  it('is one button to /auth/login with the requested return path', async () => {
    const fetch = stubSession(null, 401)
    renderAuth('/auth?return_to=/experience/sber')
    expect(screen.getByText(/Checking sign-in/i)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Continue with Google/i })).not.toBeInTheDocument()

    const button = await screen.findByRole('link', { name: /Continue with Google/i })
    expect(button).toHaveAttribute('href', '/auth/login?return_to=%2Fexperience%2Fsber')
    expect(fetch.mock.calls.map((call) => String(call[0]))).toEqual(['/auth/session'])
  })

  it('defaults the return path to the root when nothing was asked for', async () => {
    stubSession(null, 401)
    renderAuth('/auth')
    const button = await screen.findByRole('link', { name: /Continue with Google/i })
    expect(button).toHaveAttribute('href', '/auth/login?return_to=%2F')
    expect(screen.getAllByRole('link')).toHaveLength(1)
  })

  it('does not follow a return_to outside the Filenkov hosts', async () => {
    stubSession(null, 401)
    renderAuth('/auth?return_to=https://evil.example/phish')
    const button = await screen.findByRole('link', { name: /Continue with Google/i })
    expect(button).toHaveAttribute('href', '/auth/login?return_to=%2F')
  })

  it('shows the signed-in name and no sign-in button', async () => {
    stubSession(stranger)
    renderAuth('/auth')
    expect(await screen.findByText(/Signed in as/i)).toBeInTheDocument()
    expect(screen.getByText('Ann')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Continue with Google/i })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back home' })).toHaveAttribute('href', '/')
  })

  it('names a realm admin by their name, not their subject', async () => {
    stubSession(admin)
    renderAuth('/auth')
    expect(await screen.findByText('Boss')).toBeInTheDocument()
  })
})
