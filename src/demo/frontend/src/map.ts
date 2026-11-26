export type Layer = {
  id: string;
  title: string;
  kind: string;
  summary: string;
  facts: string[];
  links: string[];
  children: Layer[];
};

const host = (
  id: string,
  title: string,
  summary: string,
  facts: string[],
  links: string[],
): Layer => ({ id, title, kind: "Host", summary, facts, links, children: [] });

const leaf = (
  id: string,
  title: string,
  kind: string,
  summary: string,
  facts: string[],
  links: string[] = [],
): Layer => ({ id, title, kind, summary, facts, links, children: [] });

export const root: Layer = {
  id: "edge",
  title: "filenkov.store",
  kind: "Map",
  summary: "Three layers. Open one to see what sits inside it. A layer with nothing further is the end of that path.",
  facts: [],
  links: ["Internet names the public address.", "The router forwards that address to the server.", "The server answers on the LAN address and on the tunnel."],
  children: [
    {
      id: "internet",
      title: "Internet",
      kind: "Layer",
      summary: "Public DNS and the clients that open 443. A name is reachable from outside only when it has an A record and the router forwards the port.",
      facts: ["Public address 46.138.240.12", "One A record per name. No wildcard."],
      links: ["A record points at the router.", "The browser then opens 80 or 443."],
      children: [
        {
          id: "external-dns",
          title: "External DNS",
          kind: "DNS",
          summary: "Public A records for the names Caddy serves with Let's Encrypt. These names are not pinned in dnsmasq.",
          facts: ["Each record is 46.138.240.12", "demo.filenkov.store is the new name. It has no A record yet."],
          links: ["The resolver on the server forwards unknown names upstream."],
          children: [
            host("apex", "filenkov.store", "Apex. Resume page, sign-in, and /admin.", ["ACME certificate", "Caddy → gateway 127.0.0.1:8083"], ["Gateway route, not a Docker network of its own."]),
            host("storage", "storage.filenkov.store", "Storage product.", ["ACME", "Gateway → app:8000 on open_network"], ["Policy service(storage, family, admin). /health is public."]),
            host("image", "image.filenkov.store", "Image product.", ["ACME", "Gateway → qwen-image:8000"], ["Policy service(image, family, admin). /healthz is public."]),
            host("rag", "rag.filenkov.store", "Document chat.", ["ACME", "Gateway → rag-edge:8080 on rag_network"], ["Policy service(rag, family, admin). /health is public."]),
            host("audio", "audio.filenkov.store", "Recordings and voice notes.", ["ACME", "Gateway splits the host"], ["/api and /health → audio-api:8000. Other paths → frontend:80 on audio_network."]),
            host("llm", "llm.filenkov.store", "Model endpoint.", ["ACME", "Gateway → qwen38:4001"], ["Admin only."]),
            host("observer", "observer.filenkov.store", "Grafana.", ["ACME", "Gateway → grafana:3000"], ["Session, plus Grafana's own login. /api/health is public."]),
            host("id", "id.filenkov.store", "Keycloak. The issuer URL.", ["ACME", "Gateway → idp:8080", "Public. No LAN gate."], ["Browser follows the public issuer. The gateway calls idp on open_network."]),
            host("demo", "demo.filenkov.store", "This map.", ["ACME, once the A record exists", "Gateway → demo:80 on demo_network"], ["Session. /health is public."]),
          ],
        },
        leaf(
          "clients",
          "Clients",
          "Entry",
          "Who opens the names.",
          ["A browser on the internet, after the A record and the forward.", "A browser on the LAN, via dnsmasq.", "A VPN client, via WireGuard 10.10.0.0/24."],
          ["One session cookie on .filenkov.store for the hosts the gateway serves."],
        ),
      ],
    },
    {
      id: "router",
      title: "Router",
      kind: "Layer",
      summary: "Forwards the public address to the server at 192.168.1.102. The server does not read the router config. A missing forward looks the same as a missing DNS record.",
      facts: ["LAN gateway 192.168.1.1", "DHCP reservation for the server: 192.168.1.102"],
      links: ["80 and 443 land on Caddy.", "UDP 51820 lands on WireGuard."],
      children: [
        leaf("fwd-80", "80 → 80", "Forward", "HTTP. Caddy redirects it to HTTPS.", ["tcp 80 → 192.168.1.102:80", "Also the ACME HTTP-01 port for public names."], ["Bound by Caddy on 192.168.1.102 and 10.10.0.1."]),
        leaf("fwd-443", "443 → 443", "Forward", "HTTPS. TLS ends at Caddy.", ["tcp 443 → 192.168.1.102:443"], ["Bound by Caddy on the same two addresses."]),
        leaf("fwd-wg", "51820 → 51820", "Forward", "WireGuard. The tunnel itself, not a website.", ["udp 51820 → 192.168.1.102:51820", "The server listens on 0.0.0.0:51820 and [::]:51820."], ["Peers arrive as 10.10.0.2 and 10.10.0.4. The server side is 10.10.0.1."]),
        leaf("fwd-22", "22 → 22", "Forward", "SSH. Documented with the other forwards. Not a Caddy port.", ["tcp 22 → 192.168.1.102:22"], []),
      ],
    },
    {
      id: "server",
      title: "Server",
      kind: "Layer",
      summary: "One machine. LAN address 192.168.1.102 on enp42s0. Tunnel address 10.10.0.1 on wg0. System services answer on the host. Docker services answer on named networks.",
      facts: ["enp42s0 192.168.1.102/24", "wg0 10.10.0.1/24"],
      links: ["Caddy is the only public HTTP edge.", "Docker products are reached by the gateway, not by a published host port, except where a host port is the edge."],
      children: [
        {
          id: "wireguard",
          title: "WireGuard",
          kind: "System",
          summary: "systemd unit wg-quick@wg0. The tunnel is a second interface on this server, and a source the LAN gate trusts.",
          facts: ["Interface wg0, 10.10.0.1/24", "Listen UDP 51820", "Peers in the Caddy allow-list: 10.10.0.1, 10.10.0.2, 10.10.0.4"],
          links: ["dnsmasq listens on wg0, so tunnel clients resolve the same names as the LAN.", "Caddy binds 10.10.0.1:80 and :443."],
          children: [],
        },
        {
          id: "caddy",
          title: "Caddy",
          kind: "System",
          summary: "Host systemd. Terminates TLS, redirects HTTP to HTTPS, sets HSTS. It does not authorize. admin off, so a change is a file edit and a restart.",
          facts: [
            "Unit caddy.service",
            "Config is the git Caddyfile via /etc/caddy/Caddyfile",
            "Binds 192.168.1.102 and 10.10.0.1",
            "Protocols h1 and h2",
          ],
          links: ["Public names go to the gateway on 127.0.0.1:8083.", "Internal names stay on loopback ports and keep a LAN / WireGuard gate."],
          children: [
            {
              id: "caddy-public",
              title: "Let's Encrypt",
              kind: "Certificate",
              summary: "Public ACME HTTP-01. One certificate per name. These names reverse-proxy to the gateway.",
              facts: ["Upstream 127.0.0.1:8083", "Account admin@filenkov.store", "Needs the A record and port 80"],
              links: ["filenkov.store, storage, image, rag, audio, llm, observer, id, demo."],
              children: [],
            },
            {
              id: "caddy-internal",
              title: "Local TLS",
              kind: "Certificate",
              summary: "Caddy's local CA. Clients trust the root or they see a certificate error. Each of these names also checks the source address.",
              facts: [
                "tls internal",
                "Allow 10.10.0.1, 10.10.0.2, 10.10.0.4, 192.168.1.0/24, 127.0.0.1",
                "Anything else is 403, and the gateway never sees it",
              ],
              links: ["The names live in /etc/hosts and are answered by dnsmasq."],
              children: [
                leaf("meet", "meet.filenkov.store", "Host", "Jitsi web. Not SSO.", ["127.0.0.1:8000", "Media is UDP 10000 to the bridge, not through Caddy."]),
                leaf("hermes-host", "hermes.filenkov.store", "Host", "Hermes dashboard. Not SSO. Keeps its own login.", ["127.0.0.1:9119"]),
                leaf("lite-llm-host", "lite-llm.filenkov.store", "Host", "LiteLLM on its published port. Not a gateway host.", ["127.0.0.1:4000"]),
                leaf("registry-host", "registry.filenkov.store", "Host", "Image registry. Not a gateway host.", ["127.0.0.1:5000", "htpasswd on the registry itself."]),
              ],
            },
          ],
        },
        {
          id: "dnsmasq",
          title: "DNSmasq",
          kind: "System",
          summary: "Cache and LAN resolver. The host's resolv.conf points at 127.0.0.1. Unknown names go upstream.",
          facts: [
            "Listens on :53 for lo, enp42s0 (192.168.1.102), and wg0 (10.10.0.1)",
            "Upstreams 192.168.1.1, 8.8.8.8, 1.1.1.1",
            "interface=enp42s0 so LAN clients and rootless containers can use 192.168.1.102",
          ],
          links: ["/etc/hosts pins the internal names at 192.168.1.102.", "Public names are not pinned, so they resolve to 46.138.240.12."],
          children: [
            leaf(
              "local-names",
              "Local names",
              "DNS",
              "Pinned to 192.168.1.102. No public A record is required for these.",
              ["hermes.filenkov.store", "observer.filenkov.store", "lite-llm.filenkov.store", "meet.filenkov.store", "registry.filenkov.store"],
              ["observer also has a public A record. On this host the hosts file wins."],
            ),
          ],
        },
        {
          id: "hermes",
          title: "Hermes",
          kind: "System",
          summary: "Two systemd units. Only the dashboard is on the HTTP edge.",
          facts: ["hermes-dashboard.service listens 127.0.0.1:9119", "hermes-gateway.service is the messaging agent. It is not a Caddy host."],
          links: ["Caddy serves hermes.filenkov.store with local TLS and the LAN gate.", "The auth gateway does not authenticate it."],
          children: [],
        },
        {
          id: "docker",
          title: "Docker",
          kind: "Open-Storage",
          summary: "Namespaces in ~/projects/Open-Storage. This level is networks and who joins them. A service here is a name, a port, and the networks it sits on.",
          facts: ["One namespace is one compose file and one env file.", "The gateway joins a product network only when it has an upstream there."],
          links: ["common_network is shared data.", "open_network, rag_network, audio_network, and demo_network are the hops from the gateway."],
          children: [
            {
              id: "ns-auth",
              title: "auth-gateway",
              kind: "Namespace",
              summary: "Identity and the HTTP edge behind Caddy. The proxy itself is systemd, not a container.",
              facts: ["Compose deploy/auth-gateway", "Gateway published only on 127.0.0.1:8083 and metrics 127.0.0.1:19000"],
              links: ["Reaches product networks. Does not join common_network."],
              children: [
                {
                  id: "net-open",
                  title: "open_network",
                  kind: "Network",
                  summary: "Created here. The namespace's own services, and the storage app.",
                  facts: ["gateway", "idp :8080", "idp_db :5432", "resume :80"],
                  links: ["Gateway → idp for discovery, JWKS, token, revoke.", "Gateway → resume for the apex page.", "open-storage app joins this network as app:8000."],
                  children: [],
                },
                leaf("net-models", "models_network", "Network", "External. The image upstream and the llm server.", ["qwen-image:8000", "qwen38:4001"], ["Joined by the gateway. Not created by this repository."]),
                leaf("net-rag-join", "rag_network", "Network", "External. Created by the rag namespace.", ["rag-edge:8080"], ["The gateway's only hop into rag."]),
                leaf("net-audio-join", "audio_network", "Network", "External. Created by the audio namespace.", ["audio-api:8000", "frontend:80"], ["The gateway's only hop into audio."]),
                leaf("net-demo-join", "demo_network", "Network", "External. Created by the demo namespace.", ["demo:80"], ["The gateway's only hop into this map."]),
                leaf("net-deploy-auth", "deploy_auth_network", "Network", "External. Joined so grafana:3000 resolves.", ["grafana:3000"], ["observer.filenkov.store."]),
              ],
            },
            {
              id: "ns-common",
              title: "common",
              kind: "Namespace",
              summary: "Shared data. Other products join common_network and use the service names. Nothing here is published except MinIO.",
              facts: ["Creates common_network"],
              links: ["open-storage, rag, audio, and llm join it.", "The gateway does not."],
              children: [
                {
                  id: "net-common",
                  title: "common_network",
                  kind: "Network",
                  summary: "The only network this namespace creates.",
                  facts: ["postgres :5432", "redis :6379", "minio :9000 (also published on the host)", "rabbitmq :5672, alias rabbit", "mongo :27017"],
                  links: ["MinIO data is the disk at /media/aleksey/HardDisk/minio."],
                  children: [],
                },
              ],
            },
            {
              id: "ns-storage",
              title: "open-storage",
              kind: "Namespace",
              summary: "The storage app. It creates no network.",
              facts: ["Container open-storage-app", "DNS app:8000"],
              links: ["open_network toward the gateway.", "common_network toward postgres, redis, and minio."],
              children: [
                leaf("os-open", "open_network", "Network", "External. The gateway hop.", ["app:8000"], ["Host storage.filenkov.store."]),
                leaf("os-common", "common_network", "Network", "External. Data.", ["postgres:5432", "redis:6379", "minio:9000"], ["No RabbitMQ and no Mongo from this app."]),
              ],
            },
            {
              id: "ns-rag",
              title: "rag",
              kind: "Namespace",
              summary: "Document chat. The edge container is the only one the gateway can see.",
              facts: ["No host port"],
              links: ["rag_network is the hop.", "rag_internal is the stack.", "common_network is mongo, minio, and rabbit."],
              children: [
                leaf("rag-edge-net", "rag_network", "Network", "Created here. Gateway hop.", ["rag-edge :8080"], ["frontend is not on this network."]),
                leaf("rag-internal", "rag_internal", "Network", "Created here. Not external.", ["rag-edge", "file-collector", "processor", "deletion-worker", "chat", "frontend", "embedding", "ocr", "rag-qdrant"], ["Qdrant stays on this network only."]),
                leaf("rag-common", "common_network", "Network", "External.", ["file-collector, processor, deletion-worker, chat"], ["mongo, minio, rabbit. Not the frontend, not qdrant, not embedding, not ocr."]),
              ],
            },
            {
              id: "ns-audio",
              title: "audio",
              kind: "Namespace",
              summary: "Recordings. The gateway splits UI and API. Both are on the edge network.",
              facts: ["No host port"],
              links: ["audio_network is the hop.", "audio_internal is workers and qdrant.", "common_network is mongo, minio, rabbit, and redis."],
              children: [
                leaf("audio-edge-net", "audio_network", "Network", "Created here. Gateway hop.", ["audio-api :8000", "frontend :80"], ["Workers are not on this network."]),
                leaf("audio-internal", "audio_internal", "Network", "Created here. Not external.", ["audio-api", "diarizer", "asr-worker", "qdrant"], ["Qdrant is only here."]),
                leaf("audio-common", "common_network", "Network", "External.", ["audio-api, diarizer, asr-worker"], ["mongo, minio, rabbit, redis. Not the frontend. Not qdrant."]),
              ],
            },
            {
              id: "ns-llm",
              title: "llm",
              kind: "Namespace",
              summary: "llama.cpp and the LiteLLM router. This namespace creates no network. Both join common.",
              facts: ["Host ports 4001 and 4000, which Caddy and the gateway use from the host", "Router DNS litellm-proxy-server:4000", "Server DNS qwen38:4001"],
              links: ["Router → qwen38:4001 on common_network.", "Router → postgres database db_litellm.", "Caddy serves lite-llm.filenkov.store to 127.0.0.1:4000, outside the gateway."],
              children: [
                leaf("llm-common", "common_network", "Network", "External. Both containers.", ["litellm-proxy-server :4000", "qwen38 :4001", "postgres :5432"], ["The gateway also reaches qwen38:4001 via models_network."]),
              ],
            },
            {
              id: "ns-demo",
              title: "demo",
              kind: "Namespace",
              summary: "This page. One container, one network, no data service.",
              facts: ["Container demo-frontend", "DNS name demo, port 80", "No host publish"],
              links: ["The gateway joins demo_network after this namespace creates it."],
              children: [
                leaf("demo-net", "demo_network", "Network", "Created here.", ["demo :80"], ["Host demo.filenkov.store. Session, except /health."]),
              ],
            },
          ],
        },
      ],
    },
  ],
};

export function walk(layer: Layer, visit: (layer: Layer, parent: Layer | null) => void, parent: Layer | null = null): void {
  visit(layer, parent);
  for (const child of layer.children) walk(child, visit, layer);
}

export function findPath(layer: Layer, ids: string[]): Layer | null {
  let current = layer;
  for (const id of ids) {
    const next = current.children.find((child) => child.id === id);
    if (!next) return null;
    current = next;
  }
  return current;
}
