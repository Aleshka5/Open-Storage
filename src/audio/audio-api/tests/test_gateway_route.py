"""The `audio.filenkov.store` host in the auth-gateway config.

The config is `src/auth-gateway/gateway/config.yaml` (repo root is parents[4]
of this file). Assert only facts already in that file.
"""

from __future__ import annotations

import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[4]
CONFIG = ROOT / "src" / "auth-gateway" / "gateway" / "config.yaml"
HOST = "audio.filenkov.store"


def _load() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def _audio_host(doc: dict) -> dict:
    matches = [host for host in doc["hosts"] if host["host"] == HOST]
    assert len(matches) == 1
    return matches[0]


def test_audio_upstreams():
    doc = _load()
    assert doc["upstreams"]["audio"] == "audio-api:8000"
    assert doc["upstreams"]["audio_web"] == "frontend:80"


def test_audio_host_policy():
    host = _audio_host(_load())
    assert host["service"] == "audio"
    assert host["frame"] == "self"
    assert "microphone=(self)" in host["permissions_policy"]
    assert host["timeouts"]["response_header"] == "30m"


def test_audio_routes_in_order():
    routes = _audio_host(_load())["routes"]
    assert [route["path"] for route in routes] == ["/health", "/api/**", "/**"]
    assert routes[0]["upstream"] == "audio"
    assert routes[0]["policy"] == "public"
    assert routes[1]["upstream"] == "audio"
    assert routes[1]["policy"] == "service(audio, family, admin)"
    assert routes[2]["policy"] == "session"
