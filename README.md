# Open-Storage

Identity and edge for the `filenkov.store` hosts.

Read [AGENTS.md](AGENTS.md) for where the rules live. The system map is [docs/init.md](docs/init.md).

Namespaces are on the system map. `auth-gateway` is the edge ([how to run it](docs/auth-gateway/README.md)). `open-storage` is the storage app. `common` is Postgres, Redis, MinIO, RabbitMQ and Mongo on `common_network`.
