import { useEffect, useMemo, useState, type ChangeEvent } from 'react'
import {
  ApiError,
  fetchServices,
  fetchUsers,
  putAdmin,
  putEnabled,
  putServiceLevel,
  putServiceState,
} from '../api'
import { useAuth } from '../auth'
import {
  SERVICE_LEVELS,
  isAdmin,
  isBlockedLevel,
  levelLabel,
  levelOf,
  serviceLevel,
  withAdmin,
  withEnabled,
  withLevel,
  type Account,
  type HostBudget,
  type ManagedService,
  type ServiceLevel,
  type ServicesSnapshot,
  type ServiceState,
  type User,
} from '../types'

/** Snapshot cadence; the fast one runs while a transition is in flight. */
const SERVICE_POLL_MS = 5000
const SERVICE_POLL_BUSY_MS = 2000

const SERVICE_BUTTONS: readonly { state: ServiceState; label: string }[] = [
  { state: 'off', label: 'Off' },
  { state: 'cpu', label: 'CPU' },
  { state: 'gpu', label: 'GPU' },
]

/** MiB to GiB, one decimal — the unit the memory line promises. */
function gib(mib: number | null | undefined): string {
  if (typeof mib !== 'number' || !Number.isFinite(mib)) return '—'
  return (mib / 1024).toFixed(1)
}

/**
 * `{"error":"last_admin"}` is an answer, not a transport failure: the code is
 * shown as the message. Switch-Service still answers code+message on its own
 * routes, so that pair is kept when it carries both.
 */
function errorText(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    return err.code && err.code !== err.message ? `${err.code}: ${err.message}` : err.message
  }
  if (err instanceof Error) return err.message
  return fallback
}

function stateText(service: ManagedService, pending: boolean): string {
  if (service.transition?.phase) return service.transition.phase
  if (pending || service.busy) return service.state === 'stopping' ? 'stopping…' : 'starting…'
  if (service.state === 'ready') return service.mode ? `ready · ${service.mode}` : 'ready'
  if (service.state === 'starting') return 'starting…'
  if (service.state === 'stopping') return 'stopping…'
  if (service.state === 'failed') return 'failed'
  return 'off'
}

function serviceMemory(service: ManagedService): {
  ram: number
  ramMeasured: boolean
  vram: number
  vramMeasured: boolean
} {
  const measuredRam = service.measured?.ram_mib ?? null
  const measuredVram = service.measured?.vram_mib ?? null
  return {
    ram: measuredRam ?? service.claim?.ram_mib ?? 0,
    ramMeasured: measuredRam !== null,
    vram: measuredVram ?? service.claim?.vram_mib ?? 0,
    vramMeasured: measuredVram !== null,
  }
}

function memoryLine(host: HostBudget): { ram: string; vram: string } {
  const ram = `RAM ${gib(host.ram?.free_mib)} / ${gib(host.ram?.budget_mib)} GiB free · ${gib(host.ram?.claimed_mib)} GiB claimed`
  const vram = host.vram
    ? `VRAM ${gib(host.vram.free_mib)} / ${gib(host.vram.budget_mib)} GiB free · ${gib(host.vram.claimed_mib)} GiB claimed`
    : 'VRAM: no sample'
  return { ram, vram }
}

function ServicesSection() {
  const [snapshot, setSnapshot] = useState<ServicesSnapshot | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [loadError, setLoadError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [pendingId, setPendingId] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    let timer: ReturnType<typeof setTimeout> | undefined
    let fast = false

    const load = async () => {
      try {
        const next = await fetchServices()
        if (!alive) return
        fast = next.services.some((service) => service.busy || service.transition != null)
        setSnapshot(next)
        setStatus('ready')
        setLoadError(null)
      } catch (err) {
        if (!alive) return
        setLoadError(errorText(err, 'Could not load services'))
        setStatus((prev) => (prev === 'ready' ? prev : 'error'))
      }
    }

    const schedule = () => {
      timer = setTimeout(tick, fast ? SERVICE_POLL_BUSY_MS : SERVICE_POLL_MS)
    }

    // A hidden tab pauses the cadence, so the poll never runs while nobody watches.
    const tick = async () => {
      if (!document.hidden) await load()
      if (alive) schedule()
    }

    // The first snapshot loads even from a background tab; only repeats wait for focus.
    void load().then(() => {
      if (alive) schedule()
    })

    const onVisible = () => {
      if (document.hidden) return
      if (timer) clearTimeout(timer)
      void tick()
    }
    document.addEventListener('visibilitychange', onVisible)

    return () => {
      alive = false
      document.removeEventListener('visibilitychange', onVisible)
      if (timer) clearTimeout(timer)
    }
  }, [])

  async function switchTo(service: ManagedService, state: ServiceState): Promise<void> {
    if (pendingId) return
    setPendingId(service.id)
    setActionError(null)
    try {
      await putServiceState(service.id, state)
    } catch (err) {
      setActionError(errorText(err, 'Could not switch the service'))
    }
    try {
      setSnapshot(await fetchServices())
      setStatus('ready')
    } catch {
      // Leave the last snapshot on screen; the poll loop keeps retrying.
    } finally {
      setPendingId(null)
    }
  }

  const memory = snapshot ? memoryLine(snapshot.host) : null

  return (
    <section className="admin-services" aria-labelledby="services-heading">
      <div className="admin-head">
        <div>
          <h2 id="services-heading">Services</h2>
        </div>
      </div>
      <p className="muted admin-lead">
        Model services on this host. Pick where each one runs — the switch applies in place.
      </p>
      {memory ? (
        <p className="muted services-memory">
          <span>{memory.ram}</span>
          {' · '}
          <span>{memory.vram}</span>
        </p>
      ) : null}
      {actionError ? <div className="banner error">{actionError}</div> : null}
      {loadError ? <div className="banner error">{loadError}</div> : null}
      {status === 'loading' ? <p className="empty">Loading services…</p> : null}
      {status === 'error' && !snapshot ? (
        <p className="empty">Service status is unavailable right now.</p>
      ) : null}
      {snapshot ? (
        <div className="table-wrap">
          {snapshot.services.length === 0 ? (
            <p className="empty">No model services are registered.</p>
          ) : (
            <table aria-label="Services">
              <thead>
                <tr>
                  <th>Service</th>
                  <th>State</th>
                  <th>Memory</th>
                  <th>Runtime</th>
                </tr>
              </thead>
              <tbody>
                {snapshot.services.map((service) => {
                  const uses = serviceMemory(service)
                  const pending = pendingId === service.id
                  return (
                    <tr key={service.id}>
                      <td>{service.title}</td>
                      <td className={service.state === 'failed' ? 'status-blocked' : undefined}>
                        {stateText(service, pending)}
                      </td>
                      <td>
                        <div>
                          RAM {gib(uses.ram)} GiB{' '}
                          <span className="muted">{uses.ramMeasured ? 'measured' : 'claim'}</span>
                        </div>
                        <div>
                          VRAM {gib(uses.vram)} GiB{' '}
                          <span className="muted">{uses.vramMeasured ? 'measured' : 'claim'}</span>
                        </div>
                      </td>
                      <td>
                        <div className="segmented" role="group" aria-label={`${service.title} runtime`}>
                          {SERVICE_BUTTONS.map(({ state, label }) => {
                            const unavailable = service.unavailable_states?.[state]
                            const pressed = service.desired_state === state
                            const disabled = service.busy || pending || unavailable != null
                            return (
                              <button
                                key={state}
                                type="button"
                                className={pressed ? 'btn btn-small' : 'btn btn-small btn-ghost'}
                                aria-pressed={pressed}
                                disabled={disabled}
                                title={unavailable?.reason ?? undefined}
                                onClick={() => void switchTo(service, state)}
                              >
                                {label}
                              </button>
                            )
                          })}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      ) : null}
    </section>
  )
}

/** Acronyms keep their case; anything else gets a capital. */
const SERVICE_TITLES: Record<string, string> = {
  storage: 'Storage',
  image: 'Image',
  rag: 'RAG',
  audio: 'Audio',
}

function titleService(service: string): string {
  if (!service) return service
  return SERVICE_TITLES[service] ?? service.charAt(0).toUpperCase() + service.slice(1)
}

/**
 * A service cell is writable only for a realm admin, or for the service's own
 * admin. The edge enforces it; the disabled select says why before the click.
 */
export function canAdminister(caller: User | null, service: string): boolean {
  if (!caller) return false
  return isAdmin(caller) || serviceLevel(caller, service) === 'admin'
}

function Switch({
  checked,
  label,
  disabled,
  title,
  onChange,
}: {
  checked: boolean
  label: string
  disabled: boolean
  title?: string
  onChange: (next: boolean) => void
}) {
  return (
    <input
      type="checkbox"
      role="switch"
      className="switch"
      aria-label={label}
      aria-checked={checked}
      title={title}
      checked={checked}
      disabled={disabled}
      onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.target.checked)}
    />
  )
}

function LevelSelect({
  account,
  service,
  disabled,
  title,
  onChange,
}: {
  account: Account
  service: string
  disabled: boolean
  title?: string
  onChange: (accountId: string, service: string, level: ServiceLevel) => void
}) {
  const level = levelOf(account, service)
  return (
    <select
      aria-label={`${titleService(service)} level for ${account.email}`}
      className={isBlockedLevel(level) ? 'status-blocked' : undefined}
      value={level ?? ''}
      disabled={disabled}
      title={title}
      onChange={(e: ChangeEvent<HTMLSelectElement>) =>
        onChange(account.id, service, e.target.value === '' ? null : (e.target.value as ServiceLevel))
      }
    >
      {SERVICE_LEVELS.map((option) => (
        <option key={option ?? 'none'} value={option ?? ''}>
          {levelLabel(option)}
        </option>
      ))}
    </select>
  )
}

export function Admin() {
  const { user, loading } = useAuth()
  const [people, setPeople] = useState<Account[]>([])
  const [total, setTotal] = useState(0)
  const [emailQuery, setEmailQuery] = useState('')
  const [listState, setListState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [loadError, setLoadError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const admin = isAdmin(user)

  useEffect(() => {
    if (loading || !admin) return
    let cancelled = false
    setListState('loading')
    setLoadError(null)
    fetchUsers()
      .then((body) => {
        if (cancelled) return
        setPeople(body.users)
        setTotal(body.total)
        setListState('ready')
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setPeople([])
        setTotal(0)
        setLoadError(errorText(err, 'Could not load the catalog'))
        setListState('error')
      })
    return () => {
      cancelled = true
    }
  }, [loading, admin])

  // One column per service, in the order the session listed them.
  const columns = useMemo(() => (user?.services ?? []).map((row) => row.service), [user])
  const filtered = useMemo(() => {
    const q = emailQuery.trim().toLowerCase()
    if (!q) return people
    return people.filter((person) => person.email.toLowerCase().includes(q))
  }, [people, emailQuery])

  if (loading) {
    return <p className="muted">Checking sign-in…</p>
  }
  if (!admin) {
    // The edge answers 403 on this path for a non-admin; the page draws nothing.
    return (
      <section className="panel stack">
        <p className="kicker">Admin</p>
        <h1>Not available</h1>
        <p className="muted">This page is for realm admins.</p>
      </section>
    )
  }

  async function onLevelChange(accountId: string, service: string, level: ServiceLevel): Promise<void> {
    setBusy(true)
    setActionError(null)
    try {
      await putServiceLevel(accountId, service, level)
      setPeople((prev) => prev.map((p) => (p.id === accountId ? withLevel(p, service, level) : p)))
    } catch (err) {
      setActionError(errorText(err, 'Could not change the level'))
    } finally {
      setBusy(false)
    }
  }

  async function onAdminChange(accountId: string, value: boolean): Promise<void> {
    setBusy(true)
    setActionError(null)
    try {
      await putAdmin(accountId, value)
      setPeople((prev) => prev.map((p) => (p.id === accountId ? withAdmin(p, value) : p)))
    } catch (err) {
      // `last_admin` lands here: the switch stays where it was and the code is shown.
      setActionError(errorText(err, 'Could not change the admin flag'))
    } finally {
      setBusy(false)
    }
  }

  async function onEnabledChange(accountId: string, value: boolean): Promise<void> {
    setBusy(true)
    setActionError(null)
    try {
      await putEnabled(accountId, value)
      setPeople((prev) => prev.map((p) => (p.id === accountId ? withEnabled(p, value) : p)))
    } catch (err) {
      setActionError(errorText(err, 'Could not change the account'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="admin-head">
        <div>
          <p className="kicker">Admin</p>
          <h1>Directory</h1>
        </div>
      </div>
      <p className="muted admin-lead">
        Every account in the realm. A level applies on the next request; disabling signs the account
        out.
      </p>
      {actionError ? <div className="banner error">{actionError}</div> : null}
      {listState === 'loading' ? <p className="empty">Loading directory…</p> : null}
      {listState === 'error' ? (
        <div className="banner error">{loadError ?? 'Could not load the catalog'}</div>
      ) : null}
      {listState === 'ready' ? (
        <>
          <div className="admin-search">
            <label htmlFor="user-email">Email</label>
            <input
              id="user-email"
              name="user-email"
              type="search"
              value={emailQuery}
              autoComplete="off"
              spellCheck={false}
              placeholder="Filter by email"
              onChange={(e: ChangeEvent<HTMLInputElement>) => setEmailQuery(e.target.value)}
            />
            <span className="muted admin-count">
              {filtered.length} of {total}
            </span>
          </div>
          <div className="table-wrap">
            {people.length === 0 ? (
              <p className="empty">No accounts yet.</p>
            ) : filtered.length === 0 ? (
              <p className="empty">No one matches that email.</p>
            ) : (
              <table aria-label="Directory">
                <thead>
                  <tr>
                    <th>Email</th>
                    <th>Name</th>
                    <th>Enabled</th>
                    <th>Admin</th>
                    {columns.map((service) => (
                      <th key={service}>{titleService(service)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((person) => (
                    <tr key={person.id}>
                      <td>{person.email}</td>
                      <td>{person.name}</td>
                      <td>
                        <Switch
                          checked={person.enabled}
                          label={`Enable ${person.email}`}
                          disabled={busy}
                          onChange={(next) => void onEnabledChange(person.id, next)}
                        />
                      </td>
                      <td>
                        <Switch
                          checked={person.admin}
                          label={`Admin for ${person.email}`}
                          disabled={busy}
                          onChange={(next) => void onAdminChange(person.id, next)}
                        />
                      </td>
                      {columns.map((service) => {
                        const writable = canAdminister(user, service)
                        return (
                          <td key={service}>
                            <LevelSelect
                              account={person}
                              service={service}
                              disabled={busy || !writable}
                              title={writable ? undefined : 'You do not administer this service'}
                              onChange={onLevelChange}
                            />
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      ) : null}
      <ServicesSection />
    </>
  )
}
