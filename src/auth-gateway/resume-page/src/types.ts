/**
 * Per-service access level. `null` means no role on that service; it is a
 * value, not a missing row, because the gateway lists every configured service.
 */
export type ServiceLevel = null | 'family' | 'admin' | 'blocked'

/** One row of `services` from the gateway. */
export type ServiceEntry = {
  service: string
  level: ServiceLevel
}

/**
 * GET /auth/session — the only identity call the page makes.
 *
 * `roles` is the realm role list (only `admin` matters to the UI). `services`
 * is the per-service access list, already resolved by the gateway, so the page
 * never parses role names.
 */
export type Session = {
  subject: string
  email: string
  name: string
  roles: string[]
  services: ServiceEntry[]
}

/** The signed-in reader. The tree and its registry take a `User`. */
export type User = Session

/** One row of GET /admin/users. `services` follows the configured order. */
export type Account = {
  id: string
  email: string
  name: string
  enabled: boolean
  admin: boolean
  services: ServiceEntry[]
}

/** GET /admin/users envelope. `total` is the catalog size, not the page size. */
export type UserList = {
  users: Account[]
  total: number
}

/** The cell values of the admin table, in menu order. */
export const SERVICE_LEVELS: readonly ServiceLevel[] = [null, 'family', 'admin', 'blocked']

/** Realm `admin`, from the session's role list — never from a service level. */
export function isAdmin(user: Pick<User, 'roles'> | null | undefined): boolean {
  return Boolean(user?.roles?.includes('admin'))
}

export function isBlockedLevel(level: ServiceLevel): boolean {
  return level === 'blocked'
}

/** The level on one service. A row the session omits reads as no access. */
export function serviceLevel(
  user: Pick<User, 'services'> | null | undefined,
  service: string,
): ServiceLevel {
  return user?.services?.find((row) => row.service === service)?.level ?? null
}

/** A service link is live for family or admin on it, or for a realm admin. */
export function canUseService(user: User | null | undefined, service: string): boolean {
  if (!user) return false
  if (isAdmin(user)) return true
  const level = serviceLevel(user, service)
  return level === 'family' || level === 'admin'
}

/** The level an admin row shows for one column. */
export function levelOf(account: Account, service: string): ServiceLevel {
  return account.services?.find((row) => row.service === service)?.level ?? null
}

export function withLevel(account: Account, service: string, level: ServiceLevel): Account {
  const rest = (account.services ?? []).filter((row) => row.service !== service)
  return { ...account, services: [...rest, { service, level }] }
}

export function withAdmin(account: Account, admin: boolean): Account {
  return { ...account, admin }
}

export function withEnabled(account: Account, enabled: boolean): Account {
  return { ...account, enabled }
}

/** The select's label for a level; `null` is an empty grant, shown as a dash. */
export function levelLabel(level: ServiceLevel): string {
  return level ?? '—'
}

/** A service runtime may sit at one of three operator-selectable states. */
export type ServiceState = 'off' | 'cpu' | 'gpu'

/** Where a service actually is right now, including the in-between states. */
export type ServiceRuntimeState = 'off' | 'starting' | 'ready' | 'stopping' | 'failed'

export type HostMemory = {
  total_mib: number
  used_mib: number
  reserve_mib: number
  budget_mib: number
  claimed_mib: number
  free_mib: number
  available_mib?: number
}

export type HostCpu = {
  threads: number
  load1: number
}

export type HostDevice = {
  index: number
  name: string
  compute_cap?: string
}

/** Host memory budget for model services; `vram` is null on a machine without a GPU. */
export type HostBudget = {
  ram: HostMemory
  vram: HostMemory | null
  cpu?: HostCpu
  device?: HostDevice | null
  sampled_at?: string
  sample_source?: string
}

export type ServiceClaim = {
  ram_mib: number
  vram_mib: number
}

export type ServiceProfile = {
  available: boolean
  reason: string | null
  claim: ServiceClaim
}

export type ServiceTransition = {
  phase: string
  target_state?: ServiceState
  started_at?: string
}

/** One model service as reported by GET /api/services. */
export type ManagedService = {
  id: string
  title: string
  kind?: string
  state: ServiceRuntimeState
  mode: ServiceState | null
  desired_state: ServiceState
  pending_state?: ServiceState | null
  busy: boolean
  supported_states?: ServiceState[]
  vertices?: ServiceState[]
  transitions_allowed?: ServiceState[]
  retry_state?: ServiceState | null
  unavailable_states?: Partial<Record<ServiceState, { reason: string } | undefined>>
  preemptible?: boolean
  options?: Record<string, unknown>
  claim: ServiceClaim
  profiles?: Partial<Record<ServiceState, ServiceProfile>>
  measured?: { ram_mib: number | null; vram_mib: number | null; at?: string } | null
  over_budget?: boolean
  container?: Record<string, unknown> | null
  health?: { ok: boolean; checked_at?: string; detail?: string } | null
  consumers?: string[]
  notes?: string[]
  drift?: boolean
  fail_sticky?: boolean
  last_error?: string | null
  transition?: ServiceTransition | null
}

export type ServicesSnapshot = {
  host: HostBudget
  services: ManagedService[]
  active_transitions?: unknown[]
}
