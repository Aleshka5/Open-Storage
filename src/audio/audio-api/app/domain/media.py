"""Domain: media validation on upload (ffprobe + container allow-list).

The container comes from the ffprobe output by content, not by extension. The extension for the
MinIO key comes from the original name, lowercased and checked against the allow-list.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Extension allow-list (docs/external_contracts/minio/bucket-and-keys.md).
ALLOWED_EXTENSIONS = {"mp3", "m4a", "wav", "ogg", "opus", "flac", "webm", "mp4", "aac"}

# Containers that we accept as audio.
_ALLOWED_CONTAINERS = {
    "mp3",
    "m4a",
    "wav",
    "ogg",
    "opus",
    "flac",
    "webm",
    "mp4",
    "mov",
    "aac",
}


@dataclass(frozen=True)
class ProbeResult:
    """ffprobe result for an uploaded file."""

    content_type: str
    duration_ms: int | None
    container: str
    has_audio_stream: bool
    #: Duration the container *claims*. For an MPEG audio stream without a Xing/VBRI index
    #: this is an estimate (size ÷ first-frame bitrate) and can be tens of percent off.
    declared_duration_ms: int | None = None
    #: True when the declared duration cannot be trusted and the stream must be
    #: re-containerized with an index before it is served (seek + timeline).
    needs_index: bool = False


#: MPEG audio: layer III carries 1152 samples per frame for MPEG-1 (32/44.1/48 kHz) and
#: 576 for MPEG-2 / MPEG-2.5 (8/11.025/12/16/22.05/24 kHz).
_MPEG1_MIN_RATE = 32000


def mpeg_samples_per_frame(sample_rate: int) -> int:
    """Samples in one MPEG layer-III frame at `sample_rate` (576 for MPEG-2/2.5)."""
    return 1152 if sample_rate >= _MPEG1_MIN_RATE else 576


def measure_mpeg_duration_ms(path: Path) -> int | None:
    """True duration of an MPEG audio stream from its frame count, in ms.

    `None` when the frame count is unavailable. One full parse, no decode: for a file
    without an index this is the only trustworthy length (`duration` in the container
    header is a bitrate estimate there).
    """
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-count_frames",
        "-show_entries",
        "stream=nb_read_frames,sample_rate",
        "-of",
        "json",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        return None
    try:
        streams = json.loads(proc.stdout.decode("utf-8")).get("streams") or []
        stream = streams[0]
        frames = int(stream["nb_read_frames"])
        sample_rate = int(stream["sample_rate"])
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if frames <= 0 or sample_rate <= 0:
        return None
    return round(frames * mpeg_samples_per_frame(sample_rate) * 1000 / sample_rate)


def add_stream_index(src: Path, dst: Path) -> bool:
    """Rewrites an MPEG audio stream with a Xing/VBRI-style index (`ffmpeg -c copy`).

    The audio frames are copied, not re-encoded: only the `Info`/`Xing` frame with the
    frame count and the seek table is added. The player then knows the real duration and
    can seek by time — an indexless MP3 makes the browser estimate a wrong length and
    seek into the wrong place (adr/ADR-010).
    """
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-i",
        str(src),
        "-map",
        "0:a:0",
        "-c",
        "copy",
        "-write_xing",
        "1",
        str(dst),
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    return proc.returncode == 0 and dst.exists() and dst.stat().st_size > 0


def _fmt_name_from_container(container: str) -> str:
    """MIME approximation by container name (ffprobe returns `format_name`)."""
    mapping = {
        "mp3": "audio/mpeg",
        "m4a": "audio/mp4",
        "mp4": "audio/mp4",
        "mov": "audio/mp4",
        "wav": "audio/wav",
        "ogg": "audio/ogg",
        "opus": "audio/ogg",
        "flac": "audio/flac",
        "webm": "audio/webm",
        "aac": "audio/aac",
    }
    return mapping.get(container, "application/octet-stream")


def probe(path: Path) -> ProbeResult:
    """Runs `ffprobe -print_format json -show_format -show_streams`.

    Returns a `ProbeResult`, or a None-like signal via a `ValueError` exception if
    ffprobe could not read the file or there is no audio track. The caller turns that into
    `415 UNSUPPORTED_MEDIA`.
    """
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        raise ValueError("ffprobe could not read the file")
    try:
        data = json.loads(proc.stdout.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("ffprobe returned non-JSON") from exc

    fmt = data.get("format", {}) or {}
    container = str(fmt.get("format_name", "")).split(",")[0].strip() or ""
    container_key = container.lower()

    streams = data.get("streams", []) or []
    has_audio = any(s.get("codec_type") == "audio" for s in streams)

    if not has_audio:
        raise ValueError("no audio track")

    if container_key not in _ALLOWED_CONTAINERS:
        raise ValueError(f"container {container_key} is not in the allow-list")

    declared_ms = None
    try:
        declared_ms = int(float(fmt["duration"]) * 1000)
    except (KeyError, TypeError, ValueError):
        declared_ms = None

    # An MPEG stream without a Xing/VBRI index declares a bitrate estimate, not a length:
    # the browser then seeks by that wrong length and lands in the wrong place. Measure the
    # real duration from the frame count and mark the file for re-containerizing.
    duration_ms = declared_ms
    needs_index = False
    if container_key == "mp3":
        measured_ms = measure_mpeg_duration_ms(path)
        if measured_ms is not None:
            off_by = abs(measured_ms - (declared_ms or 0))
            tolerance = max(1000, measured_ms // 100)  # >1% and >1s is a real skew
            needs_index = declared_ms is None or off_by > tolerance
            duration_ms = measured_ms if needs_index else declared_ms

    return ProbeResult(
        content_type=_fmt_name_from_container(container_key),
        duration_ms=duration_ms,
        container=container_key,
        has_audio_stream=True,
        declared_duration_ms=declared_ms,
        needs_index=needs_index,
    )


def extension_for(filename: str) -> str:
    """Extension from the file name, lowercased, from the allow-list.

    Returns an empty string if there is no extension or it is not in the list.
    """
    suffix = Path(filename or "").suffix.lower().lstrip(".")
    return suffix if suffix in ALLOWED_EXTENSIONS else ""
