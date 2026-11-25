# open-storage

Files, photos, a private vault, resumes and quotas. One `make up` starts the app. Postgres, Redis and MinIO are already running in [common](../common/README.md).

Copy [deploy/open-storage/.env.example](../../deploy/open-storage/.env.example) to `.env` beside it, fill the empty variables, then from `deploy/open-storage/` run `make doctor` and `make up`. Bring up `deploy/common/` first. The app listens on port 8000 inside `open_network` and publishes no host port. The gateway reaches it as `app:8000`. It reaches Postgres, Redis and MinIO as `postgres:5432`, `redis:6379` and `minio:9000` on `common_network`.

How the services fit together is [init.md](init.md). The data decision is [ADR 3](adrs/3-app-on-common-data.md).
