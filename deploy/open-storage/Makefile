include ../../scripts/engine.mk
COMPOSE ?= $(ENGINE) compose -f docker-compose.yaml
APP_DIR ?= ../../src/open-storage/app

# Empty or unset values are a failed doctor. Compose interpolation uses the same names.
# MinIO's host path and root credentials live in deploy/common.
REQUIRED_ENV = REGISTRY POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD S3_ACCESS_KEY S3_SECRET_KEY

BUILT_SERVICES = app
IMAGE_REPOS = open-storage/app

.PHONY: up down restart rebuild rebuild-app release ps logs doctor test

# Recreates the app when its definition changed. Postgres, MinIO and Redis
# are the common namespace; this target does not recreate them.
up: doctor pull-images
	$(COMPOSE) up -d

# This compose has no volumes. `down` does not touch the common namespace.
down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

# A code change in the app needs a fresh image. Under podman's buildah the cached
# layer keys on the COPY instruction, not on the file contents, so a plain
# `up --build` can bake the previous source into a "new" image.
rebuild: doctor
	$(COMPOSE) build --no-cache app
	$(COMPOSE) up -d --no-deps --force-recreate --pull never app

release: doctor publish-images

rebuild-app: rebuild

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=100

# Compose must parse, and every required key in .env must be non-empty.
# A missing key exits before `up` applies any of the file.
# The value is read the way compose reads it: a bare `KEY=`, `KEY=""` and
# `KEY=   ` are all empty, even though a `[^[:space:]]` test would pass two of
# them.
doctor:
	test -f .env.example
	test -f .env
	@missing=0; \
	for key in $(REQUIRED_ENV); do \
	  value=$$(sed -n "s/^$${key}=//p" .env | tail -n 1); \
	  case "$$value" in \
	    ""|"\"\""|"''") \
	      echo "doctor: $$key is missing or empty" >&2; \
	      missing=1 ;; \
	  esac; \
	done; \
	if [ $$missing -ne 0 ]; then exit 1; fi
	$(COMPOSE) config >/dev/null
	@$(MAKE) --no-print-directory check-images
	@echo "doctor: ok"

test:
	cd $(APP_DIR) && uv sync --frozen && uv run --no-sync pytest -q

include ../../scripts/images.mk
