import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { fetchSession, logout as apiLogout } from './api'
import type { Session } from './types'

type AuthState = {
  /** The signed-in reader, or null for a guest. One field, one meaning. */
  user: Session | null
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

/**
 * One `GET /auth/session` per application load (§security). A `401` is a guest,
 * so there is nothing to retry; any other failure is reported and treated as a
 * guest, because the page decides what to show and the edge decides what to
 * allow.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const session = await fetchSession()
      setUser(session)
      setError(null)
    } catch (err) {
      setUser(null)
      setError(err instanceof Error ? err.message : 'Could not load the session')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const logout = useCallback(async () => {
    await apiLogout()
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({ user, loading, error, refresh, logout }),
    [user, loading, error, refresh, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
