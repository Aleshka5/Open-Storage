COMPOSE ?= podman compose -f docker-compose.yaml

.PHONY: up down doctor rebuild verify

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

rebuild:
	$(COMPOSE) up -d --build

doctor:
	python3 -c 'from pathlib import Path; t=Path("docker-compose.yaml").read_text(); assert "services:" in t and "open_network" in t'
	test -f .env.example
	test -f ../../.env.example
	@if command -v podman >/dev/null 2>&1; then podman compose -f docker-compose.yaml config >/dev/null; \
	elif command -v docker >/dev/null 2>&1; then docker compose -f docker-compose.yaml config >/dev/null; \
	else echo "doctor: compose CLI is not installed; file shape checked"; fi
	@echo "doctor: service code is not in the tree yet"

verify:
	@echo "verify: scripts/verify-edge.sh is not written yet" >&2
	@exit 1
