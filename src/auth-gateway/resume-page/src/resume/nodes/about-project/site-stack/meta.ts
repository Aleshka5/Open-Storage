import type { NodeMeta } from '../../../types'

const meta: NodeMeta = {
  title: 'Site stack',
  teaser: 'React and Vite in a static nginx container, behind a Go gateway that routes by YAML and injects identity.',
  order: 30,
  seo: {
    title: 'Site stack · Alexey Filenkov',
    description:
      'What this site is built from: React 19 and Vite behind a Go 1.26 gateway, Keycloak, nginx, and Caddy.',
  },
}

export default meta
