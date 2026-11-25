"""Infrastructure: RabbitMQ (pika), synchronous, on a blocking connection.

The worker spins in its own thread (not in the event loop): blocking pika is simpler and more
honest. Topology — default exchange, routing key = queue name, .retry/.dead pairs (broker.md).
Consume — `basic_get` in a loop with `prefetch=1` (one job at a time for a GPU worker).

Identical to the diarizer transport (same broker contract); reads `audio.transcription`,
writes `audio.events`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

import pika

from app.application.ports.json_queue import QUEUE_EVENTS, QUEUE_TRANSCRIPTION

logger = logging.getLogger(__name__)

_RETRY_SUFFIX = ".retry"
_DEAD_SUFFIX = ".dead"


class RabbitMQQueue:
    def __init__(self, url: str, prefetch: int = 1) -> None:
        self._url = url
        self._prefetch = prefetch
        self._params = pika.URLParameters(url)
        # The consumer thread blocks on GPU work (diarization / transcription) and cannot
        # answer AMQP heartbeats meanwhile: with the broker default of 60 s it closed the
        # connection mid-job ("missed heartbeats from client, timeout: 60s"), RabbitMQ
        # redelivered the message and the recording stayed `uploaded`. Liveness here is
        # the HTTP /health probe, not the AMQP heartbeat, so heartbeats are off.
        self._params.heartbeat = 0
        self._conn: pika.BlockingConnection | None = None
        self._channel = None

    def _ensure(self):
        if self._channel is None or self._channel.is_closed:
            self._conn = pika.BlockingConnection(self._params)
            self._channel = self._conn.channel()
        return self._channel

    def declare(self, queue: str) -> None:
        ch = self._ensure()
        retry = queue + _RETRY_SUFFIX
        dead = queue + _DEAD_SUFFIX
        ch.queue_declare(
            queue,
            durable=True,
            arguments={
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": retry,
            },
        )
        ch.queue_declare(
            retry,
            durable=True,
            arguments={
                "x-message-ttl": 30000,
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": queue,
            },
        )
        ch.queue_declare(dead, durable=True, arguments={"x-max-length": 10000})

    def publish(
        self,
        queue: str,
        body: dict[str, Any],
        *,
        message_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        ch = self._ensure()
        props = pika.BasicProperties(content_type="application/json", delivery_mode=2)
        if message_id:
            props.message_id = message_id
        if correlation_id:
            props.correlation_id = correlation_id
        ch.basic_publish(
            exchange="",
            routing_key=queue,
            body=json.dumps(body, ensure_ascii=False),
            properties=props,
        )

    def consume(self, queue: str) -> Iterator[dict[str, Any] | None]:
        """Generator: one message per step (None — the queue is empty).

        Returns the parsed dict with the service key `_delivery_tag`.
        """
        ch = self._ensure()
        ch.basic_qos(prefetch_count=self._prefetch)

        def _iter():
            while True:
                method, _props, body = ch.basic_get(queue=queue, auto_ack=False)
                if method is None:
                    yield None
                    continue
                try:
                    parsed = json.loads(body.decode("utf-8"))
                except json.JSONDecodeError:
                    logger.warning("bad_json queue=%s", queue)
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                    yield None
                    continue
                yield {"_delivery_tag": method.delivery_tag, **parsed}

        return _iter()

    def ack(self, delivery_tag: int) -> None:
        self._ensure().basic_ack(delivery_tag=delivery_tag)

    def nack(self, delivery_tag: int, *, requeue: bool = False) -> None:
        self._ensure().basic_nack(delivery_tag=delivery_tag, requeue=requeue)

    def publish_dead(self, queue: str, body: dict[str, Any]) -> None:
        """Publishes the message to `<queue>.dead` (substantive error, ADR-009).

        The DEAD action does not nack into `.retry` (otherwise the message would spin forever):
        instead the body goes straight to `.dead` and the original is acked.
        """
        ch = self._ensure()
        props = pika.BasicProperties(content_type="application/json", delivery_mode=2)
        if body.get("job_id"):
            props.message_id = body["job_id"]
        if body.get("recording_id"):
            props.correlation_id = body["recording_id"]
        ch.basic_publish(
            exchange="",
            routing_key=queue + _DEAD_SUFFIX,
            body=json.dumps(body, ensure_ascii=False),
            properties=props,
        )

    def is_available(self) -> bool:
        try:
            ch = self._ensure()
            return bool(ch and not ch.is_closed)
        except Exception:  # noqa: BLE001
            return False

    def close(self) -> None:
        if self._conn is not None and not self._conn.is_closed:
            self._conn.close()
        self._channel = None
        self._conn = None


__all__ = [
    "QUEUE_TRANSCRIPTION",
    "QUEUE_EVENTS",
    "RabbitMQQueue",
]
