COMPOSE ?= podman compose -f docker-compose.yaml
CADDYFILE ?= $(CURDIR)/Caddyfile

.PHONY: up down rebuild rebuild-gateway doctor verify verify-mvp logs mvp-config up-mvp caddy-check

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

rebuild:
	$(COMPOSE) up -d --build

# The MVP stand differs from the live one in the gateway config only: the apex
# host becomes mvp.filenkov.store (the live apex belongs to the live stack) and
# public_origin follows it. There is one Caddyfile for both stacks — it already
# routes mvp.filenkov.store and id.filenkov.store to the MVP gateway on :18080.
# Generated, not committed.
mvp-config:
	sed -e 's|^public_origin: .*|public_origin: "https://mvp.filenkov.store"|' \
	    -e 's|^  - host: filenkov.store$$|  - host: mvp.filenkov.store|' \
	    ../../src/auth-gateway/gateway/config.yaml > config.mvp.yaml
	grep -q 'host: mvp.filenkov.store' config.mvp.yaml
	caddy validate --config $(CADDYFILE) --adapter caddyfile
	@echo "mvp-config: config.mvp.yaml written; the shared Caddyfile already carries the mvp. host"

# The MVP stand: gateway on 18080 (8080 is held by jitsi-jvb) with the MVP
# config. The edge is the live one and is not touched: mvp.filenkov.store and
# id.filenkov.store are already reverse-proxied to 127.0.0.1:18080 there.
up-mvp: mvp-config
	GATEWAY_PORT=18080 GATEWAY_CONFIG_FILE=$$PWD/config.mvp.yaml $(COMPOSE) up -d --build
	@echo "up-mvp: gateway on 127.0.0.1:18080; reach it at https://mvp.filenkov.store"

# A Go source change needs this. Under podman's buildah the cached layer keys on
# the COPY instruction, not on the file contents, so `up --build` happily bakes
# the previous binary into a "new" image.
rebuild-gateway: mvp-config
	$(COMPOSE) build --no-cache gateway
	podman rm -f auth-gateway_gateway_1 || true
	GATEWAY_PORT=18080 GATEWAY_CONFIG_FILE=$$PWD/config.mvp.yaml $(COMPOSE) up -d gateway
	@echo "rebuild-gateway: image rebuilt without cache and the container recreated"

# The edge config is shared, so it is validated once, here.
caddy-check:
	caddy validate --config $(CADDYFILE) --adapter caddyfile
	@echo "caddy-check: ok"

# Everything that must be true before `up` is worth running.
doctor: caddy-check
	$(COMPOSE) config >/dev/null
	test -f .env
	test -f .env.example
	cd ../../src/auth-gateway/gateway && go build ./...
	@echo "doctor: ok"

# The stand check: one request per SSO host through the proxy and directly to the
# gateway, both probes, and the Caddyfile.
verify:
	../../scripts/golden.sh

# The MVP stand: the same check against :18080, with the generated config. The
# apex is renamed there, so the host-list drift comparison is off by design; the
# Caddyfile is the shared one.
verify-mvp: mvp-config
	GATEWAY_ADDR=$${GATEWAY_ADDR:-127.0.0.1:18080} \
	GATEWAY_CONFIG=$$PWD/config.mvp.yaml \
	CADDYFILE=$(CADDYFILE) \
	DRIFT_CHECK=0 \
	SKIP_HOSTS="filenkov.store meet.filenkov.store" \
	../../scripts/golden.sh

logs:
	$(COMPOSE) logs -f --tail=100
