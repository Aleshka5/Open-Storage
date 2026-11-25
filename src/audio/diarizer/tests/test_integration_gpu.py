"""Integration test against the real Pyannote model (GPU), if everything is up.

Skipped when torch/pyannote/CUDA are missing. It does not fabricate a result: with the
environment unavailable it honestly `skip`s. Run manually only on a GPU host (V100 sm_70) after
`uv sync --extra gpu`.
"""

from __future__ import annotations

import subprocess

import pytest


def _has_gpu_stack() -> bool:
    try:
        import torch  # noqa: PLC0415

        if not torch.cuda.is_available():
            return False
        import pyannote.audio  # noqa: F401, PLC0415

        return True
    except Exception:  # noqa: BLE001
        return False


def _has_token() -> bool:
    return bool(_token())


def _token() -> str | None:
    import os  # noqa: PLC0415

    return os.environ.get("HF_TOKEN")


def _has_ffmpeg() -> bool:
    return subprocess.run(["which", "ffmpeg"], capture_output=True).returncode == 0


need_gpu = pytest.mark.skipif(not _has_gpu_stack(), reason="no torch+pyannote+CUDA")
need_ffmpeg = pytest.mark.skipif(not _has_ffmpeg(), reason="no ffmpeg")
need_token = pytest.mark.skipif(not _has_token(), reason="no HF_TOKEN (gated)")


@need_gpu
@need_ffmpeg
@need_token
def test_real_pyannote_two_speakers(tmp_path):
    """Two different voices → the model finds ≥2 speakers, turns do not overlap.

    This is a real model run (not a stub): it downloads the gated weights with HF_TOKEN and
    runs fp16 on CUDA. Synthetic input: two tones of different pitch in sequence. Expected
    result — at least 2 speakers and sorted non-overlapping turns.
    """
    from app.infrastructure.pyannote_model import PyannoteDiarizer  # noqa: PLC0415

    # Synthetic file: two alternating tones (imitating two voices).
    wav = tmp_path / "two_speakers.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:duration=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=660:duration=2",
            "-filter_complex",
            "concat=n=2:v=0:a=1",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            wav,
        ],
        check=True,
        capture_output=True,
    )

    model = PyannoteDiarizer(
        model_name="pyannote/speaker-diarization-community-1",
        revision="3533c8cf8e369892e6b79ff1bf80f7b0286a54ee",
        device="cuda",
        hf_token=_token(),
        hf_home=str(tmp_path / "hf"),
        use_fp16=True,
    )
    model.load()
    result = model.diarize(str(wav))
    assert len(result.speakers) >= 2
    turns = result.turns
    assert [t.start_ms for t in turns] == sorted(t.start_ms for t in turns)
    for a, b in zip(turns, turns[1:], strict=False):
        assert a.end_ms <= b.start_ms


@need_gpu
@need_ffmpeg
@need_token
def test_real_pyannote_embedding_one_vector_per_file(tmp_path):
    """The note embedding is one vector of the collection dimension (ADR-007).

    A real run of `PyannoteEmbedder`: weights of the same pipeline, fp16 on CUDA.
    We check what suggestions and `PUT /api/me/voice` rely on: the vector is non-empty,
    normalized and exactly `CENTROID_DIM` long (otherwise `VOICE_INDEX_INCOMPATIBLE`),
    and a short note (`MIN_EMBED_SECONDS`) is processed without a crash.
    """
    from app.application.ports.embedding_model import EmbeddingError  # noqa: F401, PLC0415
    from app.domain.diarization import CENTROID_DIM  # noqa: PLC0415
    from app.infrastructure.pyannote_embedding import PyannoteEmbedder  # noqa: PLC0415

    wav = tmp_path / "note.wav"
    subprocess.run(
        [
            "ffmpeg", "-f", "lavfi", "-i", "sine=frequency=330:duration=2.5",
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav,
        ],
        check=True,
        capture_output=True,
    )

    model = PyannoteEmbedder(
        pipeline_model="pyannote/speaker-diarization-community-1",
        revision="3533c8cf8e369892e6b79ff1bf80f7b0286a54ee",
        device="cuda",
        hf_token=_token(),
        hf_home=str(tmp_path / "hf"),
        use_fp16=True,
    )
    model.load()
    vec = model.embed(str(wav))
    assert len(vec) == CENTROID_DIM
    norm = sum(v * v for v in vec) ** 0.5
    assert abs(norm - 1.0) < 1e-3
