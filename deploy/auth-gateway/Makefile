COMPOSE ?= podman compose -f docker-compose.yaml
CADDYFILE ?= ../../src/auth-gateway/proxy/Caddyfile

.PHONY: up down rebuild doctor verify logs

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

rebuild:
	$(COMPOSE) up -d --build

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
