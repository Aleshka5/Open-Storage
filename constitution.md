# constitution.md

Development rules that do not depend on a stack.

Read first
 - docs/init.md — namespaces and the system map.
 - docs/namespace/init.md — how the services inside one namespace interact.
 - docs/namespace/service/init.md — what that service offers.
 - adrs/init.md — decisions that bind the whole system.
 - deploy/namespace/ — env example, Makefile, and compose for that namespace. Extra Dockerfile for services keep: deploy/namespace/service/
 - src/namespace/service/ — service code. tests/ inside the service.
 - scripts/ — checks and setup scripts. See [scripts/README.md](scripts/README.md).

Documents
 - A document states the necessary facts and stops.
 - One fact has one owner. Other documents link to it.
 - README.md files are not for developing. They are an introduction for new developers or customers.
 
Decisions
 - A decision that binds the whole system goes in adrs/.
 - A decision that binds one namespace goes in docs/namespace/adrs/.
 - An ADR states the decision, the rejected options, the cost and the risk.
 - Reopen a decision only with a new argument, recorded in a new ADR.

Boundaries
 - A namespace is one network, one env file, and one compose file. It is a scope of services with common functionality.
 - A service does not take over a fact another service already owns.
 - One component sets one response header. A duplicated header is a defect.
 - Secrets come from the deploy/namespace/.env for each namespace. A literal secret in a committed file is a defect.
 - Session state lives in one store.

Change
 - One meaning has one name and one version.
 - A breaking contract change updates every consumer in the same release.
 - Invalid configuration does not start. Do not apply part of a configuration.
 - Ship one cutover. Do not add a compatibility flag or a second live contract for the same meaning.
 - An invariant is locked by a test. A comment does not lock it.
 