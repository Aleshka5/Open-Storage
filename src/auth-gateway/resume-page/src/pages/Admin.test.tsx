import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth'
import { admin, annAccount, bossAccount, errorResponse, jsonResponse, stranger } from '../test/fixtures'
import type { Account, ManagedService, ServicesSnapshot, Session } from '../types'
import { Admin, canAdminister } from './Admin'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

function managedService(overrides: Partial<ManagedService> & Pick<ManagedService, 'id' | 'title'>): ManagedService {
  return {
    state: 'off',
    mode: null,
    desired_state: 'off',
    busy: false,
    unavailable_states: {},
    claim: { ram_mib: 1024, vram_mib: 1024 },
    measured: null,
    transition: null,
    ...overrides,
  }
}

function servicesSnapshot(): ServicesSnapshot {
  return {
    host: {
      ram: {
        total_mib: 90365,
        used_mib: 40969,
        available_mib: 49396,
        reserve_mib: 8192,
        budget_mib: 82173,
        claimed_mib: 36352,
        free_mib: 45821,
      },
      vram: null,
    },
    services: [
      managedService({ id: 'ocr', title: 'OCR', state: 'ready', mode: 'cpu', desired_state: 'cpu' }),
      managedService({ id: 'llm', title: 'LLM' }),
    ],
    active_transitions: [],
  }
}

function renderAdmin() {
  return render(
    <MemoryRouter initialEntries={['/admin']}>
      <AuthProvider>
        <Routes>
          <Route path="/admin" element={<Admin />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

type Overrides = {
  session?: Session
  users?: Account[]
  list?: () => Response | Promise<Response>
  admin?: (url: string, body: unknown) => Response | Promise<Response>
  enabled?: (url: string, body: unknown) => Response | Promise<Response>
  level?: (url: string, body: unknown) => Response | Promise<Response>
}

function stubAdmin(overrides: Overrides = {}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    const body = init?.body ? JSON.parse(String(init.body)) : null

    if (url === '/auth/session') return jsonResponse(overrides.session ?? admin)
    if (url === '/api/services') return jsonResponse(servicesSnapshot())
    if (url === '/admin/users' && method === 'GET') {
      if (overrides.list) return overrides.list()
      const users = overrides.users ?? [bossAccount, annAccount]
      return jsonResponse({ users, total: users.length })
    }
    if (method === 'PATCH' && url.startsWith('/admin/users/')) {
      if (overrides.enabled) return overrides.enabled(url, body)
      return jsonResponse({ status: 'ok' })
    }
    if (method === 'PUT' && url.endsWith('/admin')) {
      if (overrides.admin) return overrides.admin(url, body)
      return jsonResponse({ status: 'ok' })
    }
    if (method === 'PUT' && url.startsWith('/admin/users/')) {
      if (overrides.level) return overrides.level(url, body)
      return jsonResponse({ status: 'ok' })
    }
    return errorResponse(`unexpected ${method} ${url}`, 500)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function directory() {
  return screen.getByRole('table', { name: 'Directory' })
}

function headerNames(): (string | null)[] {
  return within(directory())
    .getAllByRole('columnheader')
    .map((cell) => cell.textContent)
}

describe('Admin', () => {
  it('draws no catalog for a non-admin and asks for none', async () => {
    const fetchMock = stubAdmin({ session: stranger })
    renderAdmin()
    expect(await screen.findByRole('heading', { name: 'Not available' })).toBeInTheDocument()
    expect(screen.queryByRole('table', { name: 'Directory' })).not.toBeInTheDocument()
    expect(fetchMock.mock.calls.map((call) => String(call[0]))).not.toContain('/admin/users')
  })

  it('loads GET /admin/users into one table, one column per session service', async () => {
    stubAdmin()
    renderAdmin()

    expect(await screen.findByRole('heading', { name: 'Directory' })).toBeInTheDocument()
    expect(await screen.findByText('ann@example.com')).toBeInTheDocument()
    expect(screen.getByText('boss@example.com')).toBeInTheDocument()
    expect(headerNames()).toEqual(['Email', 'Name', 'Enabled', 'Admin', 'Storage', 'Image', 'RAG', 'Audio'])
  })

  it('shows each service level, with an empty grant as a dash', async () => {
    stubAdmin()
    renderAdmin()
    expect(await screen.findByText('ann@example.com')).toBeInTheDocument()

    expect(screen.getByRole('combobox', { name: 'Storage level for ann@example.com' })).toHaveValue('family')
    expect(screen.getByRole('combobox', { name: 'Image level for ann@example.com' })).toHaveValue('')
    expect(screen.getByRole('combobox', { name: 'Storage level for boss@example.com' })).toHaveValue('family')
    expect(screen.getByRole('combobox', { name: 'Image level for boss@example.com' })).toHaveValue('admin')

    const options = within(screen.getByRole('combobox', { name: 'RAG level for ann@example.com' })).getAllByRole(
      'option',
    )
    expect(options.map((option) => option.textContent)).toEqual(['—', 'family', 'admin', 'blocked'])
  })

  it('filters by email on the client, with no second request', async () => {
    const fetchMock = stubAdmin()
    const user = userEvent.setup()
    renderAdmin()
    expect(await screen.findByText('ann@example.com')).toBeInTheDocument()
    const calls = fetchMock.mock.calls.length

    await user.type(screen.getByLabelText(/email/i), 'boss@')
    expect(screen.getByText('boss@example.com')).toBeInTheDocument()
    expect(screen.queryByText('ann@example.com')).not.toBeInTheDocument()
    expect(fetchMock.mock.calls.length).toBe(calls)

    await user.clear(screen.getByLabelText(/email/i))
    expect(screen.getByText('ann@example.com')).toBeInTheDocument()
    expect(fetchMock.mock.calls.length).toBe(calls)
  })

  it('does not match on name, id or subject', async () => {
    const odd: Account = {
      id: '44444444-4444-4444-4444-444444444444',
      email: 'zzz@example.com',
      name: 'UniqueHandle',
      enabled: true,
      admin: false,
      services: [],
    }
    stubAdmin({ users: [odd] })
    const user = userEvent.setup()
    renderAdmin()
    expect(await screen.findByText('UniqueHandle')).toBeInTheDocument()

    await user.type(screen.getByLabelText(/email/i), 'UniqueHandle')
    expect(await screen.findByText('No one matches that email.')).toBeInTheDocument()
    expect(screen.queryByText('UniqueHandle')).not.toBeInTheDocument()

    await user.clear(screen.getByLabelText(/email/i))
    expect(await screen.findByText('UniqueHandle')).toBeInTheDocument()
    await user.type(screen.getByLabelText(/email/i), odd.id)
    expect(await screen.findByText('No one matches that email.')).toBeInTheDocument()

    await user.clear(screen.getByLabelText(/email/i))
    await user.type(screen.getByLabelText(/email/i), 'zzz@')
    expect(await screen.findByText('UniqueHandle')).toBeInTheDocument()
  })

  it('distinguishes an empty catalog from a search miss', async () => {
    stubAdmin({ users: [] })
    renderAdmin()
    expect(await screen.findByText('No accounts yet.')).toBeInTheDocument()
    expect(screen.queryByText('No one matches that email.')).not.toBeInTheDocument()
    expect(screen.queryByRole('table', { name: 'Directory' })).not.toBeInTheDocument()
  })

  it('shows the envelope code when GET /admin/users fails', async () => {
    stubAdmin({ list: () => errorResponse('idp_unavailable', 503) })
    renderAdmin()
    expect(await screen.findByText('idp_unavailable')).toBeInTheDocument()
    expect(screen.queryByRole('table', { name: 'Directory' })).not.toBeInTheDocument()
  })

  it('shows forbidden when the edge refuses the catalog', async () => {
    stubAdmin({ list: () => errorResponse('forbidden', 403) })
    renderAdmin()
    expect(await screen.findByText('forbidden')).toBeInTheDocument()
  })

  it('changes a service cell with PUT /admin/users/{id}/roles/{svc}', async () => {
    const fetchMock = stubAdmin()
    const user = userEvent.setup()
    renderAdmin()
    expect(await screen.findByText('ann@example.com')).toBeInTheDocument()

    await user.selectOptions(screen.getByRole('combobox', { name: 'Storage level for ann@example.com' }), 'admin')

    await waitFor(() => {
      const put = fetchMock.mock.calls.find(
        ([url, init]) =>
          String(url) === `/admin/users/${annAccount.id}/roles/storage` && init?.method === 'PUT',
      )
      expect(put).toBeTruthy()
      expect(put?.[1]?.body).toBe(JSON.stringify({ level: 'admin' }))
    })
    expect(screen.getByRole('combobox', { name: 'Storage level for ann@example.com' })).toHaveValue('admin')
  })

  it('removes a level with a null body', async () => {
    const fetchMock = stubAdmin()
    const user = userEvent.setup()
    renderAdmin()
    expect(await screen.findByText('ann@example.com')).toBeInTheDocument()

    await user.selectOptions(screen.getByRole('combobox', { name: 'Storage level for ann@example.com' }), '')

    await waitFor(() => {
      const put = fetchMock.mock.calls.find(
        ([url, init]) =>
          String(url) === `/admin/users/${annAccount.id}/roles/storage` && init?.method === 'PUT',
      )
      expect(put?.[1]?.body).toBe(JSON.stringify({ level: null }))
    })
    expect(screen.getByRole('combobox', { name: 'Storage level for ann@example.com' })).toHaveValue('')
  })

  it('grants realm admin with PUT /admin/users/{id}/admin', async () => {
    const fetchMock = stubAdmin()
    const user = userEvent.setup()
    renderAdmin()
    expect(await screen.findByText('ann@example.com')).toBeInTheDocument()

    await user.click(screen.getByRole('switch', { name: 'Admin for ann@example.com' }))

    await waitFor(() => {
      const put = fetchMock.mock.calls.find(
        ([url, init]) => String(url) === `/admin/users/${annAccount.id}/admin` && init?.method === 'PUT',
      )
      expect(put?.[1]?.body).toBe(JSON.stringify({ value: true }))
    })
    expect(screen.getByRole('switch', { name: 'Admin for ann@example.com' })).toBeChecked()
  })

  it('shows last_admin as a message and leaves the switch alone', async () => {
    stubAdmin({ admin: () => errorResponse('last_admin', 409) })
    const user = userEvent.setup()
    renderAdmin()
    expect(await screen.findByText('boss@example.com')).toBeInTheDocument()

    await user.click(screen.getByRole('switch', { name: 'Admin for boss@example.com' }))

    expect(await screen.findByText('last_admin')).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Admin for boss@example.com' })).toBeChecked()
  })

  it('blocks an account with PATCH /admin/users/{id}', async () => {
    const fetchMock = stubAdmin()
    const user = userEvent.setup()
    renderAdmin()
    expect(await screen.findByText('ann@example.com')).toBeInTheDocument()

    await user.click(screen.getByRole('switch', { name: 'Enable ann@example.com' }))

    await waitFor(() => {
      const patch = fetchMock.mock.calls.find(
        ([url, init]) => String(url) === `/admin/users/${annAccount.id}` && init?.method === 'PATCH',
      )
      expect(patch?.[1]?.body).toBe(JSON.stringify({ enabled: false }))
    })
    expect(screen.getByRole('switch', { name: 'Enable ann@example.com' })).not.toBeChecked()
  })

  it('leaves every cell writable for a realm admin', async () => {
    stubAdmin()
    renderAdmin()
    expect(await screen.findByText('ann@example.com')).toBeInTheDocument()
    for (const service of ['Storage', 'Image', 'RAG', 'Audio']) {
      expect(screen.getByRole('combobox', { name: `${service} level for ann@example.com` })).not.toBeDisabled()
    }
  })

  it('keeps the model-service section below the table', async () => {
    stubAdmin()
    renderAdmin()
    expect(await screen.findByRole('table', { name: 'Directory' })).toBeInTheDocument()
    const services = await screen.findByRole('table', { name: 'Services' })
    expect(within(services).getByText('OCR')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Services', level: 2 })).toBeInTheDocument()
  })
})

describe('canAdminister', () => {
  it('lets a realm admin write any service', () => {
    expect(canAdminister(admin, 'storage')).toBe(true)
    expect(canAdminister(admin, 'image')).toBe(true)
  })

  it('lets a service admin write only that service', () => {
    const serviceAdmin: Session = {
      ...stranger,
      services: [
        { service: 'storage', level: 'admin' },
        { service: 'image', level: null },
        { service: 'rag', level: null },
        { service: 'audio', level: null },
      ],
    }
    expect(canAdminister(serviceAdmin, 'storage')).toBe(true)
    expect(canAdminister(serviceAdmin, 'image')).toBe(false)
    expect(canAdminister(serviceAdmin, 'rag')).toBe(false)
  })

  it('lets a guest write nothing', () => {
    expect(canAdminister(null, 'storage')).toBe(false)
  })
})
