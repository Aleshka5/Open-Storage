COMPOSE ?= podman compose -f docker-compose.yaml
APP_DIR ?= ../../src/open-storage/app

# Empty or unset values are a failed doctor. Compose interpolation uses the same names.
REQUIRED_ENV = POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD S3_ACCESS_KEY S3_SECRET_KEY MINIO_DATA_PATH

.PHONY: up down restart rebuild rebuild-app ps logs doctor test

# Recreates containers whose definition changed. Postgres, MinIO and Redis are
# data services: a recreated MinIO or Postgres is an outage with a bind-mounted
# directory behind it, not a rollout. A code change in the app goes through
# `rebuild`, which recreates the app alone.
up: doctor
	$(COMPOSE) up -d

# Keeps named volumes and the MinIO bind directory. There is no target that
# removes them. Removing volumes stays a manual, deliberate act on the CLI.
down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

# A code change in the app needs a fresh image. Under podman's buildah the cached
# layer keys on the COPY instruction, not on the file contents, so a plain
# `up --build` can bake the previous source into a "new" image.
rebuild: doctor
	$(COMPOSE) build --no-cache app
	$(COMPOSE) up -d --no-deps --force-recreate app

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
	@echo "doctor: ok"

test:
	cd $(APP_DIR) && uv sync --frozen && uv run --no-sync pytest -q
