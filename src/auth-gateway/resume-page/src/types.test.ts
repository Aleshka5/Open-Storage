import { describe, expect, it } from 'vitest'
import {
  canUseService,
  isAdmin,
  isBlockedLevel,
  levelLabel,
  levelOf,
  serviceLevel,
  withAdmin,
  withEnabled,
  withLevel,
} from './types'
import { admin, annAccount, stranger } from './test/fixtures'

describe('isAdmin', () => {
  it('reads the realm role, not a service level', () => {
    expect(isAdmin(admin)).toBe(true)
    expect(isAdmin(stranger)).toBe(false)
    expect(isAdmin(null)).toBe(false)
    expect(isAdmin({ roles: ['svc:storage:admin'] })).toBe(false)
  })
})

describe('serviceLevel', () => {
  it('reads the row the gateway sent', () => {
    expect(serviceLevel(stranger, 'storage')).toBe('family')
    expect(serviceLevel(stranger, 'image')).toBeNull()
  })

  it('treats a missing row as no access', () => {
    expect(serviceLevel({ services: [] }, 'storage')).toBeNull()
    expect(serviceLevel(null, 'storage')).toBeNull()
  })
})

describe('canUseService', () => {
  it('allows family and admin, and denies null and blocked', () => {
    expect(canUseService(stranger, 'storage')).toBe(true)
    const blocked = { ...stranger, services: [{ service: 'storage', level: 'blocked' as const }] }
    expect(canUseService(blocked, 'storage')).toBe(false)
    expect(canUseService(stranger, 'rag')).toBe(false)
  })

  it('allows everything to a realm admin and nothing to a guest', () => {
    expect(canUseService(admin, 'rag')).toBe(true)
    expect(canUseService(null, 'storage')).toBe(false)
  })
})

describe('isBlockedLevel and levelLabel', () => {
  it('names the blocked level and shows an empty grant as a dash', () => {
    expect(isBlockedLevel('blocked')).toBe(true)
    expect(isBlockedLevel(null)).toBe(false)
    expect(levelLabel(null)).toBe('—')
    expect(levelLabel('family')).toBe('family')
  })
})

describe('account helpers', () => {
  it('reads the level of one column', () => {
    expect(levelOf(annAccount, 'storage')).toBe('family')
    expect(levelOf(annAccount, 'rag')).toBeNull()
  })

  it('replaces one service and leaves the rest alone', () => {
    const next = withLevel(annAccount, 'rag', 'admin')
    expect(levelOf(next, 'rag')).toBe('admin')
    expect(levelOf(next, 'storage')).toBe('family')
    expect(next.services).toHaveLength(annAccount.services.length)
  })

  it('flips the admin and enabled flags', () => {
    expect(withAdmin(annAccount, true).admin).toBe(true)
    expect(withEnabled(annAccount, false).enabled).toBe(false)
  })
})
