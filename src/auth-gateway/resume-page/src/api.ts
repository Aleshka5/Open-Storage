import type {
  ServiceLevel,
  ServiceState,
  ServicesSnapshot,
  Session,
  UserList,
} from './types'

/** One envelope for the edge and for `/admin`: `{"error":"<snake_case>"}`. */
export class ApiError extends Error {
  status: number
  /** The same snake_case string the body carried, for callers that branch on it. */
  code?: string

  constructor(status: number, message: string, code?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

type ErrorBody = {
  error?: string | { code?: string; message?: string }
  message?: string
}

async function readErrorDetail(res: Response): Promise<{ message: string; code?: string }> {
  const text = await res.text()
  if (!text) return { message: res.statusText || `Request failed (${res.status})` }
  try {
    const body = JSON.parse(text) as ErrorBody
    // The gateway envelope: the code *is* the message.
    if (typeof body.error === 'string' && body.error) {
      return { message: body.error, code: body.error }
    }
    // Switch-Service still answers `{"error":{"code":…,"message":…}}` on its own routes.
    if (body.error && typeof body.error === 'object') {
      return {
        message: body.error.message || body.error.code || text,
        code: body.error.code,
      }
    }
    return { message: body.message || text }
  } catch {
    return { message: text }
  }
}

/**
 * One call, one answer. There is no token refresh here: the gateway owns the
 * cookies, and a 401 is a fact about the caller, not a retry instruction.
 */
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    credentials: 'include',
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...init.headers,
    },
  })
  if (!res.ok) {
    const detail = await readErrorDetail(res)
    throw new ApiError(res.status, detail.message, detail.code)
  }
  if (res.status === 204) return undefined as T
  const text = await res.text()
  if (!text) return undefined as T
  return JSON.parse(text) as T
}

/** `/auth/login?return_to=…` — the one entry action. Same-origin path or absolute URL. */
export function loginPath(returnTo: string | null | undefined): string {
  if (!returnTo) return '/auth/login'
  return `/auth/login?return_to=${encodeURIComponent(returnTo)}`
}

/** GET /auth/session. `401` means guest: no second call, no retry. */
export async function fetchSession(): Promise<Session | null> {
  const res = await fetch('/auth/session', {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (res.status === 401) return null
  if (!res.ok) {
    const detail = await readErrorDetail(res)
    throw new ApiError(res.status, detail.message, detail.code)
  }
  return (await res.json()) as Session
}

/**
 * POST /auth/logout. The gateway requires `Origin` or `X-Requested-With`, so the
 * header is set explicitly rather than trusted to browser defaults.
 */
export async function logout(): Promise<void> {
  await request('/auth/logout', {
    method: 'POST',
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
  })
}

/** GET /admin/users. Tens of users; no pagination, search is on the client. */
export async function fetchUsers(): Promise<UserList> {
  const body = await request<UserList>('/admin/users')
  return { users: body.users ?? [], total: body.total ?? body.users?.length ?? 0 }
}

/** PUT /admin/users/{id}/roles/{svc} with `{ "level": … }`. */
export async function putServiceLevel(
  id: string,
  service: string,
  level: ServiceLevel,
): Promise<void> {
  await request(`/admin/users/${encodeURIComponent(id)}/roles/${encodeURIComponent(service)}`, {
    method: 'PUT',
    body: JSON.stringify({ level }),
  })
}

/** PATCH /admin/users/{id} with `{ "enabled": … }`. Disabling signs the account out. */
export async function putEnabled(id: string, enabled: boolean): Promise<void> {
  await request(`/admin/users/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify({ enabled }),
  })
}

/** PUT /admin/users/{id}/admin with `{ "value": … }`. `409 last_admin` is a normal answer. */
export async function putAdmin(id: string, value: boolean): Promise<void> {
  await request(`/admin/users/${encodeURIComponent(id)}/admin`, {
    method: 'PUT',
    body: JSON.stringify({ value }),
  })
}

/** Host budget plus every model service on it. */
export async function fetchServices(): Promise<ServicesSnapshot> {
  return request<ServicesSnapshot>('/api/services')
}

/** Asks a service to move to off/cpu/gpu. The 202 body is a transition record we do not need. */
export async function putServiceState(id: string, state: ServiceState): Promise<void> {
  await request<unknown>(`/api/services/${encodeURIComponent(id)}/state`, {
    method: 'POST',
    body: JSON.stringify({ state }),
  })
}
