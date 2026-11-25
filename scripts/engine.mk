# Container engine for the namespace Makefile.
# Podman when it is installed (the live host). Docker otherwise.
# Override with ENGINE=docker or ENGINE=podman.
ENGINE ?= $(shell if command -v podman >/dev/null 2>&1; then echo podman; else echo docker; fi)
