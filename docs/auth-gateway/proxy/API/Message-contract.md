# proxy — message contract

Caddy 2.11. One file, `Caddyfile`. Ports 80 and 443. Bind is the LAN address plus the WireGuard address.

Three jobs: terminate TLS, redirect `http://` to `https://`, set HSTS. One upstream per host: `gateway:8080`.

Proxy does not set `Permissions-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, or `Referrer-Policy`. Those depend on the host and belong to gateway. A duplicate header is a defect: browsers intersect the policies.

## Host classes

| Class | Hosts | Certificate |
|---|---|---|
| Public | `filenkov.store`, `storage.`, `image.`, `rag.`, `audio.`, `llm.`, `observer.`, `id.` | ACME HTTP-01. One A record per name. No wildcard. |
| LAN / WireGuard | `meet.filenkov.store` | `tls internal`. Clients must install the local CA root. Say so wherever this host is documented. |
| Outside SSO | `hermes.filenkov.store` → `127.0.0.1:9119`, `lite-llm.filenkov.store` → `127.0.0.1:4000` | Public ACME. Gateway does not authenticate them. |

Protocols: `h1 h2`. No HTTP/3.

## Site shape

```caddy
{
	admin off
	email admin@filenkov.store
	servers {
		protocols h1 h2
	}
}

(secure) {
	header {
		Strict-Transport-Security "max-age=31536000; includeSubDomains"
		-Server
	}
}

filenkov.store {
	import secure
	reverse_proxy gateway:8080
}

# storage, image, rag, audio, llm, observer, id — same five lines, different name.

meet.filenkov.store {
	tls internal
	@lan remote_ip 10.10.0.0/24 192.168.1.0/24 127.0.0.1
	handle @lan {
		reverse_proxy gateway:8080
	}
	respond 403
}

hermes.filenkov.store {
	import secure
	reverse_proxy 127.0.0.1:9119
}

lite-llm.filenkov.store {
	import secure
	reverse_proxy 127.0.0.1:4000
}

http://filenkov.store, http://storage.filenkov.store {
	redir https://{host}{uri} permanent
}
```

The HTTP redirect lists every site name. With `default_bind` set, Caddy does not create that redirect itself.

A new public host: DNS A record, a site block, a gateway host, then `caddy validate` and reload.

Checks: `caddy validate`, response contains `strict-transport-security`, `http://` returns `308` to `https://`.
