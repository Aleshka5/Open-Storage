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
_COMMON = _REPO / "deploy" / "common"
_COMMON_COMPOSE = _COMMON / "docker-compose.yaml"
_COMMON_ENV = _COMMON / ".env.example"
_COMMON_MAKEFILE = _COMMON / "Makefile"

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
    assert "MINIO_DATA_PATH" not in example
    assert "changeme" not in example
    assert "@postgres:5432/" in example
    assert "redis://redis:6379" in example
    assert "http://minio:9000" in example


def _network_names(service: dict) -> list[str]:
    networks = service["networks"]
    if isinstance(networks, list):
        return list(networks)
    return list(networks)


def test_compose_app_joins_open_and_common_networks() -> None:
    text = _COMPOSE.read_text()
    for banned in ("user_network", "auth_network", "rag_edge", "nginx", "open-storage-postgres"):
        assert banned not in text
    data = yaml.safe_load(text)
    assert set(data["networks"]) == {"open_network", "common_network"}
    for name in ("open_network", "common_network"):
        network = data["networks"][name]
        assert network["external"] is True
        assert network["name"] == name
    assert "volumes" not in data

    build = data["services"]["app"]["build"]
    context = (_DEPLOY / build["context"]).resolve()
    dockerfile = (context / build["dockerfile"]).resolve()
    assert dockerfile == _DOCKERFILE.resolve()
    assert dockerfile.is_file()

    services = data["services"]
    assert set(services) == {"app"}
    app = services["app"]
    assert app["container_name"] == "open-storage-app"
    assert set(_network_names(app)) == {"open_network", "common_network"}
    assert "ports" not in app

    app_aliases = app["networks"]["open_network"]["aliases"]
    assert "app" in app_aliases
    environment = app["environment"]
    assert "@postgres:5432/" in environment["DATABASE_URL"]
    assert environment["REDIS_URL"] == "redis://redis:6379"
    assert environment["S3_ENDPOINT_URL"] == "http://minio:9000"
    assert environment["SPA_STATIC_DIR"] == "/opt/spa"


def test_common_compose_matches_shared_service_names() -> None:
    text = _COMMON_COMPOSE.read_text()
    data = yaml.safe_load(text)
    assert data["name"] == "common"
    assert list(data["networks"]) == ["common_network"]
    assert data["networks"]["common_network"]["name"] == "common_network"
    assert "external" not in data["networks"]["common_network"]

    services = data["services"]
    assert set(services) == {"postgres", "redis", "minio", "rabbitmq", "mongo"}
    for name, service in services.items():
        assert service["container_name"] == name
        assert _network_names(service) == ["common_network"]

    for name in ("postgres", "redis", "rabbitmq", "mongo"):
        assert "ports" not in services[name]
    assert set(services["minio"]["ports"]) == {"9000:9000", "9001:9001"}
    assert services["rabbitmq"]["networks"]["common_network"]["aliases"] == ["rabbit"]
    assert services["minio"]["volumes"] == ["/media/aleksey/HardDisk/minio:/data"]
    assert services["postgres"]["env_file"] == [".env"]
    assert services["minio"]["env_file"] == [".env"]

    assert set(data["volumes"]) == {
        "postgres_data",
        "redis_data",
        "rabbitmq_data",
        "mongo_data",
    }
    assert "open-storage-" not in text
    assert "open_network" not in text

    example = _COMMON_ENV.read_text()
    for key in ("POSTGRES_USER=", "POSTGRES_PASSWORD=", "MINIO_ROOT_USER=", "MINIO_ROOT_PASSWORD="):
        assert key in example
    assert "POSTGRES_DB=" not in example

    makefile = _COMMON_MAKEFILE.read_text()
    assert "down:\n\t$(COMPOSE) down\n" in makefile
    assert "--volumes" not in makefile


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
    ):
        assert key in text
    assert "MINIO_DATA_PATH" not in text


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
