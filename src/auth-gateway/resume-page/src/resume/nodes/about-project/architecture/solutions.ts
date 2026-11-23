/**
 * The boxes on the architecture map. Near-identical pages would be a folder
 * each for no benefit, so they stay a data array and the node serves
 * `/about-project/architecture/:slug` from it. Imported by `meta.ts`,
 * so this file must stay free of React and of asset imports.
 *
 * A box that is not part of the running edge is not in this array. An unknown
 * slug resolves to null and the reader is sent back to the root.
 */
export type ArchitectureSolution = {
  slug: string
  title: string
  summary: string
  href?: string
}

export const architectureSolutions: ArchitectureSolution[] = [
  {
    slug: 'caddy-https',
    title: 'Caddy HTTPS',
    summary: 'Terminates TLS on :443 and redirects HTTP to HTTPS. It does not authorize.',
  },
  {
    slug: 'auth-gateway',
    title: 'Auth Gateway',
    summary:
      'Go on :8083. Routes by host and path, checks the access token, and injects identity v1.',
    href: '/auth',
  },
  {
    slug: 'idp',
    title: 'Keycloak',
    summary:
      'id.filenkov.store, public. The gateway passes the request through.',
  },
  {
    slug: 'hub',
    title: 'Hub (filenkov.store)',
    summary:
      'This page. nginx serves the files. /auth, /admin and /api/chat are the gateway.',
  },
  {
    slug: 'storage',
    title: 'Storage',
    summary: 'storage.filenkov.store. A product upstream. The gateway injects identity v1 when the route allows it.',
    href: 'https://storage.filenkov.store',
  },
  {
    slug: 'hermes',
    title: 'Hermes',
    summary: 'hermes.filenkov.store, LAN and WireGuard only. The proxy forwards it. It keeps its own login.',
    href: 'https://hermes.filenkov.store',
  },
  {
    slug: 'llm',
    title: 'Models',
    summary:
      'llm.filenkov.store is admin-only. The owl on POST /api/chat is the gateway itself.',
    href: 'https://llm.filenkov.store',
  },
  {
    slug: 'observer',
    title: 'Grafana',
    summary: 'observer.filenkov.store. A session route. Grafana keeps its own login.',
  },
]

export function solutionBySlug(slug: string | undefined): ArchitectureSolution | undefined {
  if (!slug) return undefined
  return architectureSolutions.find((item) => item.slug === slug)
}
