# Entry point for the rag stack. Every target runs from this directory:
#   cd deploy/rag && make up
# Build contexts in docker-compose.yaml are relative to this file. Five services
# build from their own src/rag/<service> directory. file-collector, processor
# and deletion-worker build from the repository root, because their image copies
# src/rag/common beside the service; their Dockerfile is deploy/rag/<service>/.
# Mongo, MinIO and RabbitMQ are the common namespace on common_network.

COMPOSE ?= podman compose -f docker-compose.yaml

SERVICES = rag-edge file-collector processor deletion-worker chat frontend embedding ocr

# Empty or unset values are a failed doctor. Compose interpolation uses the same
# names and refuses the whole file on the first empty required key.
REQUIRED_ENV = MONGODB_URI S3_ACCESS_KEY S3_SECRET_KEY LLM_API_KEY LLM_BASE_URL LLM_MODEL

.PHONY: up down restart rebuild rebuild-all ps logs doctor test

# Recreates the containers whose definition changed. The common namespace
# (mongo, minio, rabbitmq) is not this file's to recreate.
up: doctor
	$(COMPOSE) up -d

# `down` drops the stack and its networks; the qdrant and model-cache volumes stay.
down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

# A code change needs a fresh image. Under podman's buildah the cached layer keys
# on the COPY instruction, not on the file contents, so a plain `up --build` can
# bake the previous source into a "new" image. This target refreshes rag-edge;
# `rebuild-all` does every service.
rebuild: doctor
	$(COMPOSE) build --no-cache rag-edge
	$(COMPOSE) up -d --no-deps --force-recreate rag-edge

# embedding and ocr are slow on the cpu target, which this file wires.
rebuild-all: doctor
	$(COMPOSE) build --no-cache $(SERVICES)
	$(COMPOSE) up -d --force-recreate

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
	@echo "doctor: ok"

test:
	@set -e; \
	for service in $(SERVICES); do \
	  echo "== $$service"; \
	  cd ../../src/rag/$$service && uv run --no-sync pytest -q; \
	done
