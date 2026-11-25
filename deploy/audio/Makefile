# Entry point for the audio stack. Every target runs from this directory:
#   cd deploy/audio && make up
# Build contexts in docker-compose.yaml are relative to this file.
# Mongo, MinIO, RabbitMQ and Redis are the common namespace on common_network.
# Qdrant and the Hugging Face weight volume are created empty by this file.

include ../../scripts/engine.mk
COMPOSE ?= $(ENGINE) compose -f docker-compose.yaml

SERVICES = audio-api diarizer asr-worker frontend qdrant

# Empty or unset values are a failed doctor. Compose interpolation uses the same
# names and refuses the whole file on the first empty required key.
REQUIRED_ENV = REGISTRY S3_ACCESS_KEY S3_SECRET_KEY HF_TOKEN RABBITMQ_URL

BUILT_SERVICES = audio-api diarizer asr-worker frontend
IMAGE_REPOS = audio/audio-api audio/diarizer audio/asr-worker audio/frontend

.PHONY: up down restart rebuild rebuild-all release ps logs doctor test

# Recreates the containers whose definition changed. The common namespace
# (mongo, minio, rabbitmq, redis) is not this file's to recreate.
up: doctor pull-images
	$(COMPOSE) up -d

# `down` drops the stack and its networks. The qdrant and weight volumes stay.
down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

rebuild: doctor
	$(COMPOSE) build --no-cache audio-api
	$(COMPOSE) up -d --no-deps --force-recreate --pull never audio-api

rebuild-all: doctor
	$(COMPOSE) build --no-cache $(BUILT_SERVICES)
	$(COMPOSE) up -d --force-recreate --pull never

release: doctor publish-images

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=100

# Compose must parse, and every required key in .env must be non-empty.
# A missing key exits before `up` applies any of the file.
# The value is read the way compose reads it: a bare `KEY=`, `KEY=""` and
# `KEY=   ` are all empty.
doctor:
	test -f .env.example
	test -f .env
	@missing=0; \
	for key in $(REQUIRED_ENV); do \
	  value=$$(sed -n "s/^$${key}=//p" .env | tail -n 1); \
	  case "$$value" in \
	    ""|\"\"|\x27\x27) \
	      echo "doctor: $$key is missing or empty" >&2; \
	      missing=1 ;; \
	  esac; \
	done; \
	if [ $$missing -ne 0 ]; then exit 1; fi
	$(COMPOSE) config >/dev/null
	@$(MAKE) --no-print-directory check-images
	@echo "doctor: ok"

test:
	@set -e; \
	for service in audio-api diarizer asr-worker; do \
	  echo "== $$service"; \
	  cd ../../src/audio/$$service && uv run --no-sync pytest -q; \
	done

include ../../scripts/images.mk
