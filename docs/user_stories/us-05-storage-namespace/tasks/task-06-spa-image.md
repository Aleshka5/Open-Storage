# task-06 SPA in the image

Story: [US-05](../init.md)

## Outcome

An image build produces one app image that serves the API and the built SPA. The SPA is built from `src/open-storage/spa` in a Node stage and copied to `SPA_STATIC_DIR` (`/opt/spa`), which the app serves when the directory exists.

## Paths

- `deploy/open-storage/app/Dockerfile`
- `src/open-storage/app/main.py`

## Done when

`podman build` from `deploy/open-storage` produces an image with `/opt/spa/index.html`; `GET /health` answers 200 and `GET /` answers the SPA shell from the same origin; no nginx service is in the compose; the SPA's API calls are relative so they reach the same host through the gateway.
