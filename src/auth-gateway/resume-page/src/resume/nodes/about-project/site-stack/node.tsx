import { Callout, Chips, DefinitionList, Section } from '../../../../components/article'

export default function SiteStackNode() {
  return (
    <>
      <p className="lede">
        One Go process, Keycloak, and a static page. The front end is files. The decisions happen before
        those files are served.
      </p>

      <Chips
        items={[
          'React 19',
          'react-router 7',
          'Vite 8',
          'TypeScript 6',
          'Go 1.26',
          'nginx 1.27',
          'Caddy',
          'Keycloak',
          'podman compose',
        ]}
      />

      <p>
        The site you are reading is a React 19 application built by Vite and routed by react-router. It is
        compiled once — <code>tsc -b &amp;&amp; vite build</code> inside a <code>node:22-alpine</code> stage —
        and the resulting <code>dist</code> is copied into an <code>nginx:1.27-alpine</code> image that
        listens on port 80 and is never published to the internet. nginx here is a file server: no proxy
        pass, no auth module.
      </p>

      <Section title="Who decides what">
        <DefinitionList
          items={[
            {
              term: 'Caddy',
              detail:
                'Terminates TLS and redirects HTTP to HTTPS. It does not choose the application. SSO hosts and id.filenkov.store go to the gateway on :8083. id. is public. meet. goes to Jitsi and skips the gateway.',
            },
            {
              term: 'Gateway',
              detail:
                'The Go process on :8083. It matches host and path against config.yaml, verifies the access cookie, strips inbound identity headers, and injects X-Auth-Subject, X-Auth-Email, X-Auth-Name, X-Auth-Roles, and X-Auth-Session. The rate limit is 600 requests a minute per IP. /auth, /admin, and POST /api/chat are answered here.',
            },
            {
              term: 'Keycloak',
              detail:
                'Users, roles, and sessions. Google is the only login. The session cookie holds an encrypted refresh token. There is no second user directory.',
            },
            {
              term: 'nginx',
              detail:
                'The resume files. An unknown path falls back to the app shell, and react-router takes it from there. The host catch-all in the gateway is public.',
            },
          ]}
        />
      </Section>

      <Callout title="What the Go side is made of">
        <p>
          One module on Go 1.26. The direct dependencies that matter are <code>coreos/go-oidc</code> and{' '}
          <code>go-jose</code> for tokens, <code>yaml.v3</code> for the routing file, and OpenTelemetry for
          the owl's traces. No web framework. No Redis.
        </p>
      </Callout>
    </>
  )
}
