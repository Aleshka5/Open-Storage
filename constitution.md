# constitution.md

Development rules that do not depend on a stack. One list. No commentary.

Documents
 - Every document in this repository is English.
 - A document states the necessary facts and stops.
 - Prefer a new short document over a longer one.
 - One fact has one owner. Other documents link to it.
 - AGENTS.md routes to documents. It does not copy them.
 - This file holds rules. docs/repository-layout.md holds the directory map.
 - A specification change lands in the same change as the behavior it describes.

Decisions
 - A decision that binds the whole system goes in adrs/.
 - A decision that binds one namespace goes in docs/<namespace>/adrs/.
 - An ADR states the decision, the rejected options, and the cost.
 - Reopen a decision only with a new argument, recorded in a new ADR.

Boundaries
 - A namespace is one network, one env file, and one compose file.
 - A service does not take over a fact another service already owns.
 - One component sets one response header. A duplicated header is a defect.
 - Secrets come from the environment. A literal secret in a committed file is a defect.
 - The client does not supply its own identity.
 - A credential does not go in JavaScript, a URL, or a log.
 - Session state lives in one store.

Change
 - One meaning has one name and one version.
 - A breaking contract change updates every consumer in the same release.
 - Invalid configuration does not start.
 - Do not apply part of a configuration.
 - Ship one cutover. Do not add a compatibility flag or a second live contract for the same meaning.
 - An invariant is locked by a test. A comment does not lock it.
