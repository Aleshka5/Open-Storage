# Repository layout

Where files go. Behavior of a service is not described here.

Rules Group Root
 - AGENTS.md — the important comments and the routes to other documents.
 - constitution.md — development rules that do not depend on a stack.
 - .env.example — values shared by every namespace.
 - adrs/ — decisions for the whole system.
 - scripts/ — scripts for checks and setup.

Rules Group docs
 - docs/ holds documentation.
 - docs/init.md — namespaces and the architecture of all applications. A namespace is one block. A link is a requested action or a resource.
 - docs/brand-book/ — design rules that apply to any web page.
 - docs/<namespace>/ — one namespace. The services in it share one Docker network, one env file, and one compose file.
 - docs/<namespace>/init.md — that namespace, and how its services interact. No implementation detail of a single service.
 - docs/<namespace>/<service>/ — one microservice.
 - docs/<namespace>/<service>/API/Message-contract.md — the API or message contract that service offers.
 - docs/<namespace>/<service>/External-contract.md — what that service requires outside itself.
 - docs/<namespace>/frontend/ — design, and the security and backend-interaction contracts for the UI.
 - docs/<namespace>/external-contracts/ — contracts with systems outside the namespace.
 - docs/<namespace>/adrs/ — decisions accepted for that namespace.
 - docs/<namespace>/user_stories/ — backlog of finished and in-progress work.
 - docs/<namespace>/user_stories/us-XX-title/init.md — one user story.
 - docs/<namespace>/user_stories/us-XX-title/tasks/task-XX-title.md — one task of that story.
 - docs/<namespace>/README.md — the services in the namespace for a reader who is not changing code: stack, purpose, how to run.

Rules Group deploy
 - deploy/<namespace>/.env.example — environment variables for that namespace.
 - deploy/<namespace>/Makefile — up, down, doctor, and the other lifecycle targets.
 - deploy/<namespace>/docker-compose.yaml — the services of that namespace.

Rules Group src
 - src/<namespace>/ — code of the microservices in that namespace.
 - src/<namespace>/<service>/ — code of one microservice.
 - src/<namespace>/<service>/tests/ — tests of that microservice.

Rules Group Shape
 - Namespaces in use: auth-gateway. Further namespaces get the same shape (for example common, web-storage).
 - Services inside auth-gateway: proxy (Caddyfile, run by the host, in deploy/), gateway (Go module), idp (realm.json and theme), idp_db (backup scripts in postgres/), resume-page (the SPA).
 - A Go service is a module: src/<namespace>/<service>/go.mod, cmd/<service>/, internal/<package>/, Dockerfile.
 - Do not put a second copy of a contract at the old docs/services/ path.
