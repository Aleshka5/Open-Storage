"""RabbitMQ: publishing and consuming JSON messages (pika).

The queue topology is the default exchange, routing key = queue name. Messages are persistent
(delivery_mode=2). Publishing is synchronous blocking; it is called from async via an asyncio
executor when needed (the wrappers below are synchronous — the caller decides).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

import pika

logger = logging.getLogger(__name__)

# Queues held by this service (see external_contracts/rabbitmq/broker.md).
QUEUE_EVENTS = "audio.events"
QUEUE_DIARIZATION = "audio.diarization"

_RETRY_SUFFIX = ".retry"
_DEAD_SUFFIX = ".dead"


class RabbitMQQueue:
    def __init__(self, url: str, prefetch: int = 20) -> None:
        self._url = url
        self._prefetch = prefetch
        self._conn: pika.BlockingConnection | None = None
        self._channel: pika.channel.Channel | None = None

    def _ensure(self) -> pika.channel.Channel:
        if self._channel is None or self._channel.is_closed:
            params = pika.URLParameters(self._url)
            self._conn = pika.BlockingConnection(params)
            self._channel = self._conn.channel()
        return self._channel

    def declare(self, queue: str) -> None:
        """Ensures the queue topology and its .retry/.dead pair."""
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
        ch.queue_declare(
            dead,
            durable=True,
            arguments={"x-max-length": 10000},
        )

    def publish(
        self,
        queue: str,
        body: dict[str, Any],
        *,
        message_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Publishes a JSON message. Raises when the broker is unavailable."""
        ch = self._ensure()
        props = pika.BasicProperties(
            content_type="application/json",
            delivery_mode=2,
        )
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
        """Generator: unwinds one message per step (None — the queue is empty).

        Returns the parsed dict with the auxiliary key `_delivery_tag`.
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
        ch = self._ensure()
        ch.basic_ack(delivery_tag=delivery_tag)

    def nack(self, delivery_tag: int, *, requeue: bool = False) -> None:
        ch = self._ensure()
        ch.basic_nack(delivery_tag=delivery_tag, requeue=requeue)

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
