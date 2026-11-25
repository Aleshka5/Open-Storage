"""Dependency composer: assembles the port implementations into the scenarios.

The single point where infrastructure is wired into the application. In tests, fakes are plugged
in instead of the real `Container` via `Container.override(...)`.
"""

from __future__ import annotations

from typing import Any

from app.application.events_consumer import EventsApplier, StallWatchdog
from app.application.me_service import MeService
from app.application.nick_service import NickService
from app.application.poll_budget import PollBudget
from app.application.recording_service import PhraseService, RecordingService
from app.application.voice_note_service import VoiceNoteService
from app.config import Settings
from app.infrastructure.asr_stream import WebsocketAsrStreamFactory
from app.infrastructure.minio_store import MinioAudioStore
from app.infrastructure.mongo import MongoRecordingRepo
from app.infrastructure.mongo_voice import MongoVoiceRepo
from app.infrastructure.qdrant import QdrantVoiceIndex
from app.infrastructure.rabbitmq import RabbitMQQueue


class Container:
    """Singleton holding the assembled dependency graph."""

    _instance: Container | None = None

    def __init__(
        self,
        settings: Settings,
        *,
        repo: Any = None,
        store: Any = None,
        queue: Any = None,
        voice_repo: Any = None,
        voice_index: Any = None,
        asr_factory: Any = None,
    ) -> None:
        self.settings = settings
        self.repo = repo
        self.store = store
        self.queue = queue
        # Voice repo/index — UC-9/UC-10 (suggestions + nick) and UC-5 (phrase reading). The port
        # is declared before the scenarios, since PhraseService reads phrases through it.
        self.voice_repo = voice_repo
        self.voice_index = voice_index
        self.asr_factory = asr_factory
        # US-08: the phrase polling budget. `limit=0` — disabled, counts nothing.
        self.poll_budget = PollBudget(settings.poll_budget_per_minute)
        self.recording_service = RecordingService(self.repo, self.store, self.queue, settings)
        self.phrase_service = PhraseService(self.repo, settings, voice_repo=self.voice_repo)
        self.events_applier = EventsApplier(self.repo)
        self.stall_watchdog = StallWatchdog(self.repo, settings)
        self.nick_service = NickService(
            self.voice_repo,
            self.voice_index,
            settings,
        )
        # US-07: the default "Me" voice — the `owner_voices` pointer + a `kind=me` point.
        self.me_service = MeService(
            self.repo,
            self.voice_repo,
            self.voice_index,
            settings,
        )
        self.voice_note_service = VoiceNoteService(
            self.repo,
            self.voice_repo,
            self.store,
            self.asr_factory,
            settings,
            queue=self.queue,
        )
        self.mongo_client = None
        self.mongo_db = None

    @classmethod
    def instance(cls) -> Container:
        if cls._instance is None:
            raise RuntimeError("Container is not initialized")
        return cls._instance

    @classmethod
    def build(cls, settings: Settings) -> Container:
        import motor.motor_asyncio

        client = motor.motor_asyncio.AsyncIOMotorClient(
            settings.mongo_url,
            appname="audio-api",
            maxPoolSize=settings.mongo_max_pool_size,
            serverSelectionTimeoutMS=5000,
        )
        db = client[settings.mongo_db]
        repo = MongoRecordingRepo(db)
        voice_repo = MongoVoiceRepo(db)
        store = MinioAudioStore(
            endpoint_url=settings.s3_endpoint_url,
            bucket=settings.s3_bucket,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            region=settings.s3_region,
            use_path_style=settings.s3_use_path_style,
        )
        queue = RabbitMQQueue(
            settings.rabbitmq_url, prefetch=settings.rabbitmq_prefetch
        )
        voice_index = QdrantVoiceIndex(
            settings.qdrant_url,
            collection=settings.qdrant_collection,
            api_key=settings.qdrant_api_key,
        )
        asr_factory = WebsocketAsrStreamFactory()
        c = cls(
            settings,
            repo=repo,
            store=store,
            queue=queue,
            voice_repo=voice_repo,
            voice_index=voice_index,
            asr_factory=asr_factory,
        )
        c.mongo_client = client
        c.mongo_db = db
        cls._instance = c
        return c

    @classmethod
    def set_instance(cls, c: Container) -> None:
        cls._instance = c
