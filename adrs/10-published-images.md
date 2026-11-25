# ADR-0010 Published images

## Status

Accepted

## Decision

Images this repository builds are published to the host in `REGISTRY` and run from there. The name is `$REGISTRY/<namespace>/<service>`. A release tags the build machine's local date, `YYYY-MM-DD`, and moves `latest` to that same image. `make up` pulls the tag in `IMAGE_TAG`, or `latest` when `IMAGE_TAG` is unset, and does not build. `make release` and `make up` are separate machines' commands. The procedure is [images.md](../docs/images.md).

Third-party images stay on their upstream registries. `common` publishes nothing. Registry credentials are the container engine's login, not a key in the env file.

## Rejected

A registry host written into the compose file. A date tag alone, which makes the other machine learn the date outside the registry. Building on the machine that serves traffic. Copying Postgres, Keycloak, Qdrant and the other upstream images into this registry.

## Cost

`make up` needs a registry it can pull from, and a release that already pushed the tag. A second release on the same date replaces that date tag. `make rebuild` still builds from source on a machine that has it, and the next `make up` pulls the published tag again.

## Risk

`latest` moves on every release. The next `make up` runs that image. An older date tag is the way back: set `IMAGE_TAG` to that date. Within one calendar day the date tag is not a permanent name.
