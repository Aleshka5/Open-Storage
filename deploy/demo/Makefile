# Entry point for the demo map. Every target runs from this directory:
#   cd deploy/demo && make up

include ../../scripts/engine.mk
COMPOSE ?= $(ENGINE) compose -f docker-compose.yaml

SERVICES = frontend
REQUIRED_ENV = REGISTRY
BUILT_SERVICES = frontend
IMAGE_REPOS = demo/frontend

.PHONY: up down restart rebuild rebuild-all release ps logs doctor

up: doctor pull-images
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

rebuild: doctor
	$(COMPOSE) build --no-cache frontend
	$(COMPOSE) up -d --no-deps --force-recreate --pull never frontend

rebuild-all: rebuild

release: doctor publish-images

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=100

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

include ../../scripts/images.mk
