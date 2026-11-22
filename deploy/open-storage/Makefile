COMPOSE ?= podman compose -f docker-compose.yaml
APP_DIR ?= ../../src/open-storage/app

# Empty or unset values are a failed doctor. Compose interpolation uses the same names.
REQUIRED_ENV = POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD S3_ACCESS_KEY S3_SECRET_KEY MINIO_DATA_PATH

.PHONY: up down restart rebuild ps logs doctor test

up: doctor
	$(COMPOSE) up -d

# Keeps named volumes.
down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

rebuild: doctor
	$(COMPOSE) up -d --build

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=100

# Compose must parse, and every required key in .env must be non-empty.
# A missing key exits before `up` applies any of the file.
doctor:
	test -f .env.example
	test -f .env
	@missing=0; \
	for key in $(REQUIRED_ENV); do \
	  if ! grep -Eq "^$${key}=[^[:space:]]+" .env; then \
	    echo "doctor: $$key is missing or empty" >&2; \
	    missing=1; \
	  fi; \
	done; \
	if [ $$missing -ne 0 ]; then exit 1; fi
	$(COMPOSE) config >/dev/null
	@echo "doctor: ok"

test:
	cd $(APP_DIR) && uv sync --frozen && uv run --no-sync pytest -q
