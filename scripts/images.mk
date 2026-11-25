# Publish and pull the images this namespace builds.
# Include after the namespace default target. The including file sets
# COMPOSE, ENGINE, BUILT_SERVICES and IMAGE_REPOS (paths under REGISTRY, no tag).
# The procedure is docs/images.md.

DATE := $(shell date +%Y-%m-%d)

ifeq ($(REGISTRY),)
REGISTRY := $(shell sed -n 's/^REGISTRY=//p' .env 2>/dev/null | tail -n 1)
endif

ifeq ($(IMAGE_TAG),)
IMAGE_TAG := $(shell sed -n 's/^IMAGE_TAG=//p' .env 2>/dev/null | tail -n 1)
endif
ifeq ($(IMAGE_TAG),)
IMAGE_TAG := latest
endif

ifeq ($(ENGINE),podman)
BUILD_FLAGS ?= --no-cache
else
BUILD_FLAGS ?=
endif

.PHONY: check-images pull-images publish-images

check-images:
	@test -f .env || { echo "doctor: .env is missing" >&2; exit 1; }
	@test -n "$(REGISTRY)" || { echo "doctor: REGISTRY is missing or empty" >&2; exit 1; }
	@set -eu; \
	cfg=$$(IMAGE_TAG="$(IMAGE_TAG)" REGISTRY="$(REGISTRY)" $(COMPOSE) config); \
	for repo in $(IMAGE_REPOS); do \
	  printf '%s\n' "$$cfg" | grep -F "$(REGISTRY)/$$repo:$(IMAGE_TAG)" >/dev/null || { \
	    echo "doctor: missing image $(REGISTRY)/$$repo:$(IMAGE_TAG)" >&2; \
	    exit 1; \
	  }; \
	done
	@echo "check-images: $(IMAGE_TAG)"

pull-images:
	@test -n "$(REGISTRY)" || { echo "pull: REGISTRY is missing or empty" >&2; exit 1; }
	IMAGE_TAG="$(IMAGE_TAG)" REGISTRY="$(REGISTRY)" $(COMPOSE) pull $(BUILT_SERVICES)

publish-images:
	@test -n "$(REGISTRY)" || { echo "release: REGISTRY is missing or empty" >&2; exit 1; }
	IMAGE_TAG="$(DATE)" REGISTRY="$(REGISTRY)" $(COMPOSE) build $(BUILD_FLAGS) $(BUILT_SERVICES)
	IMAGE_TAG="$(DATE)" REGISTRY="$(REGISTRY)" $(COMPOSE) push $(BUILT_SERVICES)
	@set -eu; \
	for repo in $(IMAGE_REPOS); do \
	  $(ENGINE) tag "$(REGISTRY)/$$repo:$(DATE)" "$(REGISTRY)/$$repo:latest"; \
	  $(ENGINE) push "$(REGISTRY)/$$repo:latest"; \
	done
	@echo "release: $(DATE) pushed to $(REGISTRY); latest moved"
