import { Link } from 'react-router-dom'
import type { NodeProps } from '../../../types'
import { architectureSolutions, solutionBySlug } from './solutions'

/**
 * One body, two modes. With a `slug` it renders a single box from the map;
 * without one it renders the map itself.
 */
export default function ArchitectureNode({ slug }: NodeProps) {
  if (slug) return <SolutionBody slug={slug} />
  return <MapBody />
}

function SolutionBody({ slug }: { slug: string }) {
  const solution = solutionBySlug(slug)
  if (!solution) return null

  const external = /^https?:\/\//.test(solution.href ?? '')

  return (
    <>
      <p className="lede">{solution.summary}</p>
      <p>
        A dedicated write-up for this box is not here yet. Where it sits and what it is trusted for are the
        summary above.
      </p>
      {solution.href ? (
        <p>
          <a href={solution.href} {...(external ? { rel: 'noreferrer' } : {})}>
            Open the service
          </a>
        </p>
      ) : null}
    </>
  )
}

function MapBody() {
  return (
    <>
      <p className="lede">
        The edge as it runs. Caddy terminates TLS. The gateway decides who may pass, except for the names
        Caddy serves itself.
      </p>

      <p>
        Caddy listens on <code>:80</code> and <code>:443</code>. The SSO hosts and <code>id.filenkov.store</code>{' '}
        go to the gateway on <code>:8083</code>. <code>id.</code> is public. <code>meet.filenkov.store</code> goes
        to Jitsi on <code>:8000</code> and never
        reaches the gateway. Hermes does the same kind of bypass, to its own port, and keeps its own login.
      </p>

      <p>
        The gateway matches host and path, strips identity headers the client sent, and injects identity v1
        on the hosts that ask for it. <code>filenkov.store</code> is this page: nginx holds the files, and{' '}
        <code>/auth</code>, <code>/admin</code>, and <code>/api/chat</code> are answered in the gateway.
        Keycloak owns users, roles, and sessions. There is no second identity service and no Redis on this
        path.
      </p>

      <ul>
        {architectureSolutions.map((item) => (
          <li key={item.slug}>
            <Link to={`/about-project/architecture/${item.slug}`}>
              <strong>{item.title}</strong>
            </Link>{' '}
            — {item.summary}
          </li>
        ))}
      </ul>
    </>
  )
}
