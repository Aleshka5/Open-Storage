"""Locks the open-storage namespace shape: compose, env example, image, SPA shell."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import yaml
from pydantic.aliases import AliasChoices

from config import (
    AuthSettings,
    BusinessLogicSettings,
    CacheDBSettings,
    DatabaseSettings,
    LoggingSettings,
    RagSettings,
    S3Settings,
    SpaSettings,
    StorageSettings,
)

_REPO = Path(__file__).resolve().parents[4]
_DEPLOY = _REPO / "deploy" / "open-storage"
_COMPOSE = _DEPLOY / "docker-compose.yaml"
_DOCKERFILE = _DEPLOY / "app" / "Dockerfile"
_ENV_EXAMPLE = _DEPLOY / ".env.example"
_MAKEFILE = _DEPLOY / "Makefile"

_OMITTED_FROM_EXAMPLE = {
    "USER_SERVICE_URL",
    "USER_SERVICE_TIMEOUT_MS",
    "USER_SERVICE_CACHE_TTL_SECONDS",
    "AUTH_COOKIE_NAME",
}

_SETTINGS_MODELS = (
    DatabaseSettings,
    CacheDBSettings,
    StorageSettings,
    S3Settings,
    AuthSettings,
    BusinessLogicSettings,
    LoggingSettings,
    SpaSettings,
    RagSettings,
)


def _aliases(model: type) -> set[str]:
    names: set[str] = set()
    for field in model.model_fields.values():
        alias = field.validation_alias
        if alias is None:
            continue
        if isinstance(alias, AliasChoices):
            names.update(str(choice) for choice in alias.choices)
        else:
            names.add(str(alias))
    return names


def test_env_example_lists_settings_aliases_and_omits_identity_era_names() -> None:
    example = _ENV_EXAMPLE.read_text()
    expected = set().union(*(_aliases(model) for model in _SETTINGS_MODELS))
    missing = sorted(name for name in expected - _OMITTED_FROM_EXAMPLE if name not in example)
    assert missing == []
    for name in _OMITTED_FROM_EXAMPLE:
        assert name not in example
    assert "RAG_ENABLED=false" in example
    assert "MINIO_DATA_PATH=" in example
    assert "changeme" not in example


def test_compose_joins_only_external_open_network() -> None:
    text = _COMPOSE.read_text()
    for banned in ("common_network", "user_network", "auth_network", "rag_edge", "nginx"):
        assert banned not in text
    data = yaml.safe_load(text)
    assert list(data["networks"]) == ["open_network"]
    network = data["networks"]["open_network"]
    assert network["external"] is True
    assert network["name"] == "open_network"

    build = data["services"]["app"]["build"]
    context = (_DEPLOY / build["context"]).resolve()
    dockerfile = (context / build["dockerfile"]).resolve()
    assert dockerfile == _DOCKERFILE.resolve()
    assert dockerfile.is_file()

    services = data["services"]
    assert set(services) == {"app", "postgres", "minio", "redis"}
    for name, service in services.items():
        assert "ports" not in service
        assert service["container_name"] == f"open-storage-{name}"
        assert list(service["networks"]) == ["open_network"]

    app_aliases = services["app"]["networks"]["open_network"]["aliases"]
    assert "app" in app_aliases
    environment = services["app"]["environment"]
    assert "open-storage-postgres" in environment["DATABASE_URL"]
    assert environment["REDIS_URL"] == "redis://open-storage-redis:6379"
    assert environment["S3_ENDPOINT_URL"] == "http://open-storage-minio:9000"
    assert environment["SPA_STATIC_DIR"] == "/opt/spa"

    volumes = data["volumes"]
    assert set(volumes) == {
        "open-storage-postgres-data",
        "open-storage-redis-data",
        "open-storage-minio-data",
    }
    for key, spec in volumes.items():
        assert key.startswith("open-storage-")
        assert spec["name"] == key
    device = volumes["open-storage-minio-data"]["driver_opts"]["device"]
    assert "MINIO_DATA_PATH" in device
    assert "/media/" not in text


def test_make_down_keeps_volumes() -> None:
    text = _MAKEFILE.read_text()
    assert "down:\n\t$(COMPOSE) down\n" in text
    assert "--volumes" not in text
    assert " down -v" not in text
    assert "REQUIRED_ENV" in text
    for key in (
        "POSTGRES_PASSWORD",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
        "MINIO_DATA_PATH",
    ):
        assert key in text


def test_dockerfile_builds_spa_into_the_app_image() -> None:
    text = _DOCKERFILE.read_text()
    lowered = text.lower()
    assert "nginx" not in lowered
    assert "vite dev" not in lowered
    assert "FROM node:20-alpine AS frontend" in text
    assert "COPY spa/" in text
    assert "npm run build" in text
    assert "COPY --from=frontend /frontend/dist /opt/spa" in text
    assert "ENV SPA_STATIC_DIR=/opt/spa" in text


def test_spa_index_and_health_when_static_dir_is_populated(tmp_path: Path) -> None:
    index = tmp_path / "index.html"
    index.write_text("<!doctype html><title>open-storage</title><p>spa-shell</p>")
    (tmp_path / "assets").mkdir()
    script = textwrap.dedent(
        """
        import os
        from fastapi.testclient import TestClient
        import main

        client = TestClient(main.app)
        health = client.get("/health")
        assert health.status_code == 200, health.text
        assert health.json() == {"status": "ok"}
        root = client.get("/")
        assert root.status_code == 200, root.text
        assert "spa-shell" in root.text
        assert "text/html" in root.headers["content-type"]
        nested = client.get("/files")
        assert nested.status_code == 200
        assert "spa-shell" in nested.text
        """
    )
    env = os.environ.copy()
    env["SPA_STATIC_DIR"] = str(tmp_path)
    env["RAG_ENABLED"] = "false"
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=_REPO / "src" / "open-storage" / "app",
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
