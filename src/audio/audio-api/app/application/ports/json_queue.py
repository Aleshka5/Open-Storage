"""Message queue port (RabbitMQ)."""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol


class JsonQueue(Protocol):
    """Publishes and consumes JSON messages on named queues."""

    def publish(
        self,
        queue: str,
        body: dict[str, Any],
        *,
        message_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Publishes a message. Raises when the broker is unavailable."""
        ...

    def declare(self, queue: str) -> None:
        ...

    def consume(self, queue: str) -> Iterator[dict[str, Any] | None]:
        """Message generator; None — the queue is empty at this step."""
        ...

    def ack(self, delivery_tag: int) -> None:
        ...

    def nack(self, delivery_tag: int, *, requeue: bool = False) -> None:
        ...

    def is_available(self) -> bool:
        ...

    def close(self) -> None:
        ...
