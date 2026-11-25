"""Application ports — the contracts infrastructure implements.

Scenarios depend only on these protocols; tests plug in fakes.
"""

from app.application.ports.audio_store import AudioStore
from app.application.ports.json_queue import JsonQueue
from app.application.ports.recording_repo import RecordingRepo

__all__ = ["AudioStore", "JsonQueue", "RecordingRepo"]
