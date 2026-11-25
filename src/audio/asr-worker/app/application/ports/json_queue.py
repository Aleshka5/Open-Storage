"""Queue port: publishing JSON messages and delivery control.

asr-worker reads `audio.transcription` and publishes `audio.events`. The
nack/ack/requeue/publish_dead behaviour comes from the rabbitmq/broker.md and
queue-audio-* contracts.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol


class JsonQueue(Protocol):
    def declare(self, queue: str) -> None: ...

    def publish(
        self,
        queue: str,
        body: dict[str, Any],
        *,
        message_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None: ...

    def consume(self, queue: str) -> Iterator[dict[str, Any] | None]: ...

    def ack(self, delivery_tag: int) -> None: ...

    def nack(self, delivery_tag: int, *, requeue: bool = False) -> None: ...

    def publish_dead(self, queue: str, body: dict[str, Any]) -> None: ...

    def is_available(self) -> bool: ...

    def close(self) -> None: ...


# Queue names (external_contracts/rabbitmq/broker.md).
QUEUE_TRANSCRIPTION = "audio.transcription"
QUEUE_EVENTS = "audio.events"
