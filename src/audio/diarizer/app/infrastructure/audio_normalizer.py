"""Infrastructure: normalization via ffmpeg/ffprobe as a subprocess.

Flags are fixed (ADR-014): `ffmpeg -ac 1 -ar 16000 -c:a pcm_s16le`. Neither Pyannote nor
the model leaks in here — decoding only.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.application.ports.audio_normalizer import NormalizeError


def normalize(src_path: str, dst_path: str) -> None:
    """Decodes the source into a WAV (16 kHz mono s16le) next to it."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        src_path,
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        dst_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0 or not Path(dst_path).is_file():
        # Do not log stderr in full: no texts or paths in logs (constitution §10).
        raise NormalizeError("ffmpeg failed to decode the source")


def probe_duration_ms(path: str) -> int | None:
    """Audio duration in ms via ffprobe. None if the file cannot be read."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout.decode("utf-8"))
        return int(float(data["format"]["duration"]) * 1000)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
