COMPOSE ?= podman compose -f docker-compose.yaml
CADDYFILE ?= ../../src/auth-gateway/proxy/Caddyfile

.PHONY: up down rebuild doctor verify logs mvp-config up-mvp

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

rebuild:
	$(COMPOSE) up -d --build

# The MVP host set: the same file with the hub renamed to mvp.filenkov.store and
# the public origin moved with it. Generated, not committed — one source of truth.
mvp-config:
	sed -e 's|^public_origin: .*|public_origin: "https://mvp.filenkov.store"|' \
	    -e 's|^  - host: filenkov.store$$|  - host: mvp.filenkov.store|' \
	    ../../src/auth-gateway/gateway/config.yaml > config.mvp.yaml
	grep -q 'host: mvp.filenkov.store' config.mvp.yaml
	@echo "mvp-config: config.mvp.yaml written"

# The MVP stack: gateway on 18080 (8080 is held by jitsi-jvb) with the MVP config.
up-mvp: mvp-config
	GATEWAY_PORT=18080 GATEWAY_CONFIG_FILE=$$PWD/config.mvp.yaml $(COMPOSE) up -d --build
	@echo "up-mvp: gateway on 127.0.0.1:18080, mvp.filenkov.store in its config"

# Everything that must be true before `up` is worth running.
doctor:
	$(COMPOSE) config >/dev/null
	test -f .env
	test -f .env.example
	test -f $(CADDYFILE)
	caddy validate --config $(CADDYFILE) --adapter caddyfile
	cd ../../src/auth-gateway/gateway && go build ./...
	@echo "doctor: ok"

# The stand check: one request per SSO host through the proxy and directly to the
# gateway, both probes, and the Caddyfile.
verify:
	../../scripts/golden.sh

logs:
	$(COMPOSE) logs -f --tail=100
