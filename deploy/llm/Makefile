include ../../scripts/engine.mk
COMPOSE ?= $(ENGINE) compose -f docker-compose.yaml

# Empty or unset values are a failed doctor. Same names as .env.example.
REQUIRED_ENV = LLM_API_KEY LITELLM_MASTER_KEY DATABASE_URL

.PHONY: up down restart ps logs doctor

up: doctor
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=100

# Compose must parse, and every required key in .env must be non-empty.
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
