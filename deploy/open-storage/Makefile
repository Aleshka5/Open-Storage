COMPOSE ?= podman compose -f docker-compose.yaml
APP_DIR ?= ../../src/open-storage/app

.PHONY: up down restart rebuild ps logs doctor test

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

rebuild:
	$(COMPOSE) up -d --build

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=100

# Everything that must be true before `up` is worth running: the compose file
# parses, the env example is present, and the secrets an operator must supply
# are set in .env.
doctor:
	$(COMPOSE) config >/dev/null
	test -f .env.example
	test -f .env
	grep -q '^POSTGRES_PASSWORD=.\+' .env
	grep -q '^S3_ACCESS_KEY=.\+' .env
	grep -q '^S3_SECRET_KEY=.\+' .env
	@echo "doctor: ok"

# The app's suite, in a throwaway venv, from the code root.
test:
	cd $(APP_DIR) && uv sync --frozen && uv run --no-sync pytest -q
