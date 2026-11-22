# open-storage

Files, photos, a private vault, resumes and quotas. One `make up` starts the app, Postgres, MinIO and Redis.

Copy [deploy/open-storage/.env.example](../../deploy/open-storage/.env.example) to `.env` beside it, fill the empty variables, then from `deploy/open-storage/` run `make doctor` and `make up`. The app listens on port 8000 inside `open_network` and publishes no host port. The gateway reaches it as `app:8000`. `make down` leaves the named volumes in place.

How the services fit together is [init.md](init.md). The namespace decision is [ADR 1](adrs/1-own-data-on-open-network.md).
