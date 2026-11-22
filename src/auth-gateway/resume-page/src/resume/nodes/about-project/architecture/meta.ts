import type { NodeMeta } from '../../../types'
import { solutionBySlug } from './solutions'

const meta: NodeMeta = {
  title: 'Architecture',
  teaser: 'TLS at Caddy, routing in the gateway, and the hosts that edge actually fronts.',
  order: 20,
  seo: {
    title: 'Architecture · Alexey Filenkov',
    description:
      'The edge behind filenkov.store: Caddy, the Go gateway, Keycloak on the LAN, and the hosts the gateway fronts.',
  },
  /**
   * A dozen near-identical solution pages would be a dozen folders for no benefit, so
   * `/about-project/architecture/<slug>` is served from this node's body.
   * Returning null for an unknown slug is what sends a bad URL back to the root.
   */
  dynamicChild: {
    resolve: (slug) => {
      const solution = solutionBySlug(slug)
      return solution ? { title: solution.title, teaser: solution.summary } : null
    },
  },
}

export default meta
