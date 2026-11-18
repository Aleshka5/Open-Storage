# ADR-0004 Config is applied by restart

## Status

Accepted

## Decision

Gateway validates `config.yaml` at start. Any change is a restart. No file watch, no partial apply, no warning-only validation.

## Rejected

Hot reload, or a soft validation that starts anyway.

## Cost

Routes cannot change without a restart. Acceptable: this edge is not highly available, and a restart does not sign people out.

## Because

A deleted route that silently falls through to a SPA catch-all is a long diagnosis. An explicit trailing `/**` per host, and unreachable routes as startup errors, remove that class. A half-applied config is worse than the previous config.
