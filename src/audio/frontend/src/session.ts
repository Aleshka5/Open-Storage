import { apiUrl } from './api/base';

/** Gate for the workspace. The gateway owns the cookie; this call only learns whether it was accepted. */

export type Gate = 'checking' | 'guest' | 'ready' | 'forbidden' | 'error';

export async function probeAccess(): Promise<Exclude<Gate, 'checking'>> {
  try {
    const res = await fetch(apiUrl('/api/me'), {
      credentials: 'include',
      headers: { Accept: 'application/json' },
    });
    if (res.status === 401) return 'guest';
    if (res.status === 403) return 'forbidden';
    if (!res.ok) return 'error';
    return 'ready';
  } catch {
    return 'error';
  }
}
