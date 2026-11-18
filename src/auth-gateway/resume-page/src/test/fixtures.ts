import { vi } from 'vitest'
import type { Account, Session } from '../types'

/**
 * Ann: signed in, family on Storage, no realm admin. `services` lists every
 * configured service, the way the gateway answers, with `null` for "no role".
 */
export const stranger: Session = {
  subject: '11111111-1111-1111-1111-111111111111',
  email: 'ann@example.com',
  name: 'Ann',
  roles: [],
  services: [
    { service: 'storage', level: 'family' },
    { service: 'image', level: null },
    { service: 'rag', level: null },
    { service: 'audio', level: null },
  ],
}

/** Boss: realm admin, so every service link is live. */
export const admin: Session = {
  ...stranger,
  subject: '22222222-2222-2222-2222-222222222222',
  email: 'boss@example.com',
  name: 'Boss',
  roles: ['admin'],
  services: [
    { service: 'storage', level: 'family' },
    { service: 'image', level: 'admin' },
    { service: 'rag', level: null },
    { service: 'audio', level: null },
  ],
}

/** The `/admin/users` row for a session. */
export function accountOf(session: Session, overrides: Partial<Account> = {}): Account {
  return {
    id: session.subject,
    email: session.email,
    name: session.name,
    enabled: true,
    admin: session.roles.includes('admin'),
    services: session.services,
    ...overrides,
  }
}

export const annAccount: Account = accountOf(stranger)

export const bossAccount: Account = accountOf(admin)

export function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** The one error envelope: `{"error":"<snake_case>"}`. */
export function errorResponse(code: string, status: number): Response {
  return jsonResponse({ error: code }, status)
}

export function mockFetch(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
    return handler(url, init)
  })
  vi.stubGlobal('fetch', fn)
  return fn
}
