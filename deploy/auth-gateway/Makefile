COMPOSE ?= podman compose -f docker-compose.yaml
CADDYFILE ?= ../../src/auth-gateway/proxy/Caddyfile

.PHONY: up down rebuild rebuild-gateway doctor verify verify-mvp logs mvp-config up-mvp

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

# A Go source change needs this. Under podman's buildah the cached layer keys on
# the COPY instruction, not on the file contents, so `up --build` happily bakes
# the previous binary into a "new" image.
rebuild-gateway: mvp-config
	$(COMPOSE) build --no-cache gateway
	podman rm -f auth-gateway_gateway_1 || true
	GATEWAY_PORT=18080 GATEWAY_CONFIG_FILE=$$PWD/config.mvp.yaml $(COMPOSE) up -d gateway
	@echo "rebuild-gateway: image rebuilt without cache and the container recreated"

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

# The MVP stand: the same check against :18080 and the generated host set. The
# apex is renamed there, so the host-list drift comparison is off by design.
verify-mvp: mvp-config
	GATEWAY_ADDR=$${GATEWAY_ADDR:-127.0.0.1:18080} \
	GATEWAY_CONFIG=$$PWD/config.mvp.yaml \
	DRIFT_CHECK=0 \
	SKIP_HOSTS="filenkov.store meet.filenkov.store" \
	../../scripts/golden.sh

logs:
	$(COMPOSE) logs -f --tail=100
