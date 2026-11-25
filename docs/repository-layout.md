# Repository layout

Where files go. Behavior of a service is not described here.

Root
 - adrs/ — decisions for the whole system.
 - scripts/ — scripts for checks and setup.

Docs
 - docs/ holds documentation.
 - docs/init.md — namespaces and the architecture of all applications. A namespace is one block. A link is a requested action or a resource.
 - docs/brand-book/ — general design rules that apply to any web page.
 - docs/user_stories/ — backlog of features.
 - docs/user_stories/us-XX-title/init.md — one user story.
 - docs/user_stories/us-XX-title/tasks/task-XX-title.md — one task of that story.

Docs Namespace
 - docs/<namespace>/ — main folder of namespace. The services in it share one Docker network, one env file, and one compose file.
 - docs/<namespace>/init.md — namespace entry description, service level architecture and how its services interact. No implementation detail of a single service.
 - docs/<namespace>/frontend/ — design, and the security and backend-interaction contracts for the UI.
 - docs/<namespace>/external-contracts/ — contracts with systems outside the namespace.
 - docs/<namespace>/adrs/ — decisions accepted for that namespace.
 - docs/<namespace>/README.md — the services in the namespace for a reader who is not changing code: stack, purpose, how to run.

Docs Service
 - docs/<namespace>/<service>/ — one microservice docs.
 - docs/<namespace>/<service>/api-contract.md — the API contract that service offers.
 - docs/<namespace>/<service>/external-contract.md — what that service requires outside itself.

Rules Group deploy
 - deploy/<namespace>/.env.example — environment variables for that namespace.
 - deploy/<namespace>/Makefile — up, down, doctor, and the other lifecycle targets. Image publish and pull: [images.md](images.md).
 - deploy/<namespace>/docker-compose.yaml — the services of that namespace.
 - deploy/<namespace>/<service>/Dockerfile - service dockerfile if needed

Rules Group src
 - src/<namespace>/ — code of the microservices in that namespace.
 - src/<namespace>/<service>/ — code of one microservice.
 - src/<namespace>/<service>/tests/ — tests of that microservice.
