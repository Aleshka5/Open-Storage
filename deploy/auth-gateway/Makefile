COMPOSE ?= podman compose -f docker-compose.yaml
CADDYFILE ?= $(CURDIR)/Caddyfile

# The live gateway port. Declared here as well as in .env: compose falls back to
# 8080 (`${GATEWAY_PORT:-8080}`) when the variable is unset, and the Caddyfile
# sends every SSO host to 8083, so an unset port is a 502 on every host.
GATEWAY_PORT ?= 8083
GATEWAY_ADDR ?= 127.0.0.1:$(GATEWAY_PORT)
GATEWAY_CONFIG_FILE ?= $(abspath ../../src/auth-gateway/gateway/config.yaml)

.PHONY: up down rebuild rebuild-gateway doctor verify verify-edge caddy-check logs

up: doctor
	GATEWAY_PORT=$(GATEWAY_PORT) $(COMPOSE) up -d
	@echo "up: gateway on 127.0.0.1:$(GATEWAY_PORT)"

down:
	$(COMPOSE) down

rebuild: doctor
	GATEWAY_PORT=$(GATEWAY_PORT) $(COMPOSE) up -d --build

# A Go source change needs this. Under podman's buildah the cached layer keys on
# the COPY instruction, not on the file contents, so `up --build` happily bakes
# the previous binary into a "new" image.
rebuild-gateway:
	$(COMPOSE) build --no-cache gateway
	$(COMPOSE) rm -sf gateway
	GATEWAY_PORT=$(GATEWAY_PORT) GATEWAY_CONFIG_FILE=$(GATEWAY_CONFIG_FILE) $(COMPOSE) up -d gateway
	@echo "rebuild-gateway: image rebuilt without cache; gateway on 127.0.0.1:$(GATEWAY_PORT)"

# The edge config is shared, so it is validated once, here.
caddy-check:
	caddy validate --config $(CADDYFILE) --adapter caddyfile
	@echo "caddy-check: ok"

# Everything that must be true before `up` is worth running.
doctor: caddy-check
	$(COMPOSE) config >/dev/null
	test -f .env
	test -f .env.example
	test -f $(GATEWAY_CONFIG_FILE)
	cd ../../src/auth-gateway/gateway && go build ./...
	@echo "doctor: ok"

# verify-edge alone, without the probes. Takes the same variables as the script:
# AUTH_COOKIE_SIGNED_IN, AUTH_COOKIE_ADMIN. The gateway address follows
# GATEWAY_PORT, so the run hits the stand `make up` actually started.
verify-edge:
	GATEWAY_ADDR=$(GATEWAY_ADDR) ../../scripts/verify-edge.sh

# The stand check: one request per SSO host through the proxy and directly to the
# gateway, both probes, and the Caddyfile. GATEWAY_ADDR reaches both the edge
# check and the probes.
verify:
	GATEWAY_ADDR=$(GATEWAY_ADDR) CADDYFILE=$(CADDYFILE) ../../scripts/golden.sh

logs:
	$(COMPOSE) logs -f --tail=100
