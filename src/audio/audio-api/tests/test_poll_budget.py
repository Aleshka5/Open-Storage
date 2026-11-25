"""Phrase polling budget → `429 RATE_LIMITED` (US-08, item 9).

The 180 requests/min per IP limit is held by the gateway (ADR-005). Per contract the client doubles
the interval up to 6 s on a `429`. Here the service's **voluntary** counter is checked:

- `POLL_BUDGET_PER_MINUTE` requests pass inside the window, the next one is `429 RATE_LIMITED`
  in the usual error envelope;
- the window slides: after 60 s the budget is free again;
- the budget is counted per owner: a foreign poll does not eat mine;
- by default (`0`) it is off — the product behaviour does not change;
- upload and recording reads are not limited by the budget (only phrase polling).

The clock is injected into `PollBudget`, so the test does not sleep for a minute.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.application.poll_budget import PollBudget
from app.domain.app_error import AppError
from app.domain.errors import ErrorCode
from app.presentation.api import create_app
from app.presentation.container import Container
from tests.conftest import OTHER_OWNER, OWNER


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_budget_allows_limit_then_429():
    clock = FakeClock()
    budget = PollBudget(3, clock=clock)
    for _ in range(3):
        budget.check(OWNER)
    with pytest.raises(AppError) as exc:
        budget.check(OWNER)
    assert exc.value.code is ErrorCode.RATE_LIMITED
    assert exc.value.http_status == 429


def test_window_slides_after_a_minute():
    clock = FakeClock()
    budget = PollBudget(2, clock=clock)
    budget.check(OWNER)
    budget.check(OWNER)
    clock.advance(59.0)
    with pytest.raises(AppError):
        budget.check(OWNER)
    clock.advance(1.5)  # 60.5 s since the first request — the window is free
    budget.check(OWNER)


def test_budget_is_per_owner():
    budget = PollBudget(1, clock=FakeClock())
    budget.check(OWNER)
    budget.check(OTHER_OWNER)  # a foreign owner must not suffer
    with pytest.raises(AppError):
        budget.check(OWNER)


def test_disabled_budget_never_raises():
    budget = PollBudget(0)
    assert budget.enabled is False
    for _ in range(1000):
        budget.check(OWNER)


def test_negative_limit_is_treated_as_disabled():
    """`POLL_BUDGET_PER_MINUTE=-1` does not unlock the limit, it disables it."""
    budget = PollBudget(-5)
    assert budget.enabled is False
    budget.check(OWNER)


def test_budget_logs_rate_limited(caplog):
    budget = PollBudget(1, clock=FakeClock())
    budget.check(OWNER)
    with caplog.at_level("WARNING"):
        with pytest.raises(AppError):
            budget.check(OWNER)
    assert any("RATE_LIMITED" in r.message for r in caplog.records)
    # The offender in the log — by owner prefix, not the full UUID.
    assert OWNER not in caplog.text


@pytest.fixture
def client_factory(settings, repo, voice_repo, voice_index, store, queue):
    def _build(limit: int) -> TestClient:
        s = settings.model_copy(update={"poll_budget_per_minute": limit})
        c = Container(
            s,
            repo=repo,
            store=store,
            queue=queue,
            voice_repo=voice_repo,
            voice_index=voice_index,
        )
        # The clock is fixed: the test does not depend on real time.
        c.poll_budget = PollBudget(limit, clock=FakeClock())
        Container.set_instance(c)
        return TestClient(create_app(s), raise_server_exceptions=False)

    return _build


def test_phrases_endpoint_returns_429_over_budget(client_factory, repo):
    client = client_factory(2)
    headers = {"X-Auth-Subject": OWNER}
    rid = "3b9c7a54-1e2d-4c88-9f01-77aa0c3e5b21"

    first = client.get(f"/api/recordings/{rid}/phrases", headers=headers)
    second = client.get(f"/api/recordings/{rid}/phrases", headers=headers)
    third = client.get(f"/api/recordings/{rid}/phrases", headers=headers)

    # The first two pass the budget: 404 (no recording in the fake) or 200, but not 429.
    assert first.status_code != 429
    assert second.status_code != 429
    assert third.status_code == 429
    detail = third.json()["detail"]
    assert detail["error_code"] == "RATE_LIMITED"
    assert "message" in detail


def test_budget_does_not_limit_listing(client_factory):
    """Only phrase polling is limited; listing and recording details do not spend the budget."""
    client = client_factory(1)
    headers = {"X-Auth-Subject": OWNER}
    for _ in range(5):
        assert client.get("/api/recordings", headers=headers).status_code != 429


def test_default_settings_leave_budget_off(settings):
    """The product does not introduce its own limit by default: the gateway holds it."""
    assert settings.poll_budget_per_minute == 0
    c = Container(
        settings,
        repo=None,
        store=None,
        queue=None,
        voice_repo=None,
        voice_index=None,
    )
    assert c.poll_budget.enabled is False
