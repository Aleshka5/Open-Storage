/** Same-origin API root. `VITE_API_BASE_URL` is empty in production, so calls stay on this host. */

export function apiUrl(path: string): string {
  const origin = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');
  const suffix = path.startsWith('/') ? path : `/${path}`;
  return `${origin}${suffix}`;
}
