"""ASR stream client port: the `asr-worker /v1/stream` connection.

`audio-api` is the only client of this socket (the browser does not go here). The port abstracts
the live channel to `asr-worker` so tests can plug in a fake without a network. Frame format —
`docs/backend/asr-worker/api.md`: first a text `{type:open, ...}`, then binary PCM,
the server sends `ready/partial/final/done/error`.
"""

from __future__ import annotations

from typing import Any, Protocol


class AsrStreamError(Exception):
    """The stream service is unavailable or refused with an ASR error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code  # ASR_UNAVAILABLE | ASR_BUSY | ...
        self.message = message


class AsrStream(Protocol):
    """A live recognition channel to asr-worker for one note."""

    async def open(self, *, recording_id: str, phrase_id: str, owner_id: str) -> None:
        """Opens the session (sends `open`). Raises AsrStreamError when busy/refused.

        `ASR_BUSY` — the slot is taken by another note (`4503`), `ASR_UNAVAILABLE` — the service
        is unavailable. Before `recv` the server may return an error frame or close the socket.
        """

    async def send_pcm(self, data: bytes) -> None:
        """Sends one PCM s16le 16 kHz frame (≤ 64 KB)."""
        ...

    async def send_stop(self) -> None:
        """Sends `{type: stop}` — read out the remainder and finalize."""

    async def recv(self) -> dict[str, Any] | None:
        """The next server message (dict) or None on close `1000`.

        The keys are `type` (`ready`|`partial`|`final`|`done`|`error`) plus fields per contract.
        """

    @property
    def close_code(self) -> int | None:
        """The asr socket close code (None if still open)."""

    async def close(self) -> None:
        """Closes the socket."""


class AsrStreamFactory(Protocol):
    """Creates the stream client for `audio-api` (tests plug in a fake)."""

    def connect(self, ws_url: str) -> AsrStream:
        """Returns a ready (but not yet opened) client for `ws_url`."""
