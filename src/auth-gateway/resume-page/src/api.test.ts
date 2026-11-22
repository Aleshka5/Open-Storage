import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  fetchServices,
  fetchSession,
  fetchUsers,
  loginPath,
  logout,
  putAdmin,
  putEnabled,
  putServiceLevel,
  putServiceState,
} from './api'
import { admin, annAccount, bossAccount, errorResponse, jsonResponse, stranger } from './test/fixtures'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

function fetchMock(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
    return handler(url, init)
  })
  vi.stubGlobal('fetch', fn)
  return fn
}

describe('loginPath', () => {
  it('omits return_to when absent', () => {
    expect(loginPath(null)).toBe('/auth/login')
    expect(loginPath(undefined)).toBe('/auth/login')
  })

  it('encodes return_to', () => {
    expect(loginPath('/experience/sber?a=1')).toBe(
      '/auth/login?return_to=%2Fexperience%2Fsber%3Fa%3D1',
    )
  })
})

describe('fetchSession', () => {
  it('reads GET /auth/session once and keeps the parsed services', async () => {
    const fetch = fetchMock(async (url) => {
      if (url === '/auth/session') return jsonResponse(stranger)
      return errorResponse('unexpected', 500)
    })
    await expect(fetchSession()).resolves.toEqual(stranger)
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch.mock.calls[0][1]).toMatchObject({ credentials: 'include' })
  })

  it('treats 401 as a guest without a second call', async () => {
    const fetch = fetchMock(async () => errorResponse('unauthorized', 401))
    await expect(fetchSession()).resolves.toBeNull()
    expect(fetch.mock.calls.map((call) => String(call[0]))).toEqual(['/auth/session'])
  })

  it('throws ApiError with the envelope code on other failures', async () => {
    fetchMock(async () => errorResponse('idp_unavailable', 503))
    await expect(fetchSession()).rejects.toMatchObject({
      name: 'ApiError',
      status: 503,
      message: 'idp_unavailable',
      code: 'idp_unavailable',
    })
  })
})

describe('logout', () => {
  it('posts /auth/logout with X-Requested-With and cookies', async () => {
    const fetch = fetchMock(async () => jsonResponse({ status: 'ok' }))
    await logout()
    expect(fetch.mock.calls[0][0]).toBe('/auth/logout')
    expect(fetch.mock.calls[0][1]).toMatchObject({ method: 'POST', credentials: 'include' })
    expect(fetch.mock.calls[0][1]?.headers).toMatchObject({ 'X-Requested-With': 'XMLHttpRequest' })
  })
})

describe('admin api', () => {
  it('loads the catalog from GET /admin/users', async () => {
    const fetch = fetchMock(async (url) => {
      if (url === '/admin/users') {
        return jsonResponse({ users: [bossAccount, annAccount], total: 2 })
      }
      return errorResponse('unexpected', 500)
    })
    await expect(fetchUsers()).resolves.toEqual({ users: [bossAccount, annAccount], total: 2 })
    expect(fetch.mock.calls[0][0]).toBe('/admin/users')
    expect(fetch.mock.calls[0][1]).toMatchObject({ credentials: 'include' })
    expect(JSON.stringify(fetch.mock.calls[0][1]?.headers)).not.toMatch(/Authorization/i)
  })

  it('puts a service level, including removing it with null', async () => {
    const fetch = fetchMock(async () => jsonResponse({ status: 'ok' }))
    await putServiceLevel(annAccount.id, 'storage', 'admin')
    await putServiceLevel(annAccount.id, 'rag', null)
    expect(fetch.mock.calls.map((call) => [String(call[0]), call[1]?.method, call[1]?.body])).toEqual([
      [`/admin/users/${annAccount.id}/roles/storage`, 'PUT', JSON.stringify({ level: 'admin' })],
      [`/admin/users/${annAccount.id}/roles/rag`, 'PUT', JSON.stringify({ level: null })],
    ])
  })

  it('patches enabled and puts the admin flag', async () => {
    const fetch = fetchMock(async () => jsonResponse({ status: 'ok' }))
    await putEnabled(admin.subject, false)
    await putAdmin(admin.subject, true)
    expect(fetch.mock.calls.map((call) => [String(call[0]), call[1]?.method, call[1]?.body])).toEqual([
      [`/admin/users/${admin.subject}`, 'PATCH', JSON.stringify({ enabled: false })],
      [`/admin/users/${admin.subject}/admin`, 'PUT', JSON.stringify({ value: true })],
    ])
  })

  it('keeps last_admin as a message, not a network error', async () => {
    fetchMock(async () => errorResponse('last_admin', 409))
    await expect(putAdmin(admin.subject, false)).rejects.toMatchObject({
      name: 'ApiError',
      status: 409,
      message: 'last_admin',
    })
  })
})

describe('switch-service api', () => {
  const host = {
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
  }

  it('loads the snapshot from GET /api/services', async () => {
    const fetch = fetchMock(async (url) => {
      if (url === '/api/services') return jsonResponse({ host, services: [], active_transitions: [] })
      return errorResponse('unexpected', 500)
    })
    await expect(fetchServices()).resolves.toMatchObject({ services: [], host: { vram: null } })
    expect(fetch.mock.calls[0][1]).toMatchObject({ credentials: 'include' })
  })

  it('posts the requested state and ignores the 202 transition body', async () => {
    const fetch = fetchMock(async (url) => {
      if (url === '/api/services/ocr/state') {
        return jsonResponse({ noop: false, transition: { phase: 'starting' } }, 202)
      }
      return errorResponse('unexpected', 500)
    })
    await expect(putServiceState('ocr', 'gpu')).resolves.toBeUndefined()
    expect(fetch.mock.calls[0][1]).toMatchObject({
      method: 'POST',
      body: JSON.stringify({ state: 'gpu' }),
    })
  })

  it('keeps the switch-service code next to the message', async () => {
    fetchMock(async () =>
      jsonResponse({ error: { code: 'INSUFFICIENT_VRAM', message: 'Not enough VRAM for gpu' } }, 409),
    )
    await expect(putServiceState('ocr', 'gpu')).rejects.toMatchObject({
      name: 'ApiError',
      status: 409,
      code: 'INSUFFICIENT_VRAM',
      message: 'Not enough VRAM for gpu',
    })
  })
})

describe('ApiError', () => {
  it('keeps the status and the code', () => {
    const err = new ApiError(409, 'last_admin', 'last_admin')
    expect(err.status).toBe(409)
    expect(err.message).toBe('last_admin')
  })
})
