"""`PyannoteDiarizer._load_waveform` — the torchcodec-free input path.

Structural test: no weights, no GPU, no token. It checks what the stand actually depends
on — that `norm.wav` becomes a `{"waveform": (1, N) float32, "sample_rate": 16000}` dict
(the shape pyannote takes instead of a file path) and that anything not 16 kHz mono s16le
is refused with a code instead of being silently resampled (ADR-014).

Skipped when torch is missing (unit env without `--extra gpu`).
"""

from __future__ import annotations

import struct
import wave

import pytest

torch = pytest.importorskip("torch")

from app.application.ports.diarizer_model import ModelLoadError  # noqa: E402
from app.infrastructure.pyannote_model import PyannoteDiarizer  # noqa: E402


def _diarizer() -> PyannoteDiarizer:
    return PyannoteDiarizer(
        model_name="pyannote/speaker-diarization-community-1",
        revision="deadbeef",
        device="cpu",
        hf_token=None,
        hf_home="/tmp",
    )


def _write_wav(path, *, rate: int, channels: int, frames: int = 1600, width: int = 2):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(struct.pack("<" + "h" * frames, *([1000] * frames)))


def test_load_waveform_16k_mono_s16le(tmp_path):
    p = tmp_path / "norm.wav"
    _write_wav(p, rate=16000, channels=1, frames=1600)

    out = _diarizer()._load_waveform(str(p))

    assert out["sample_rate"] == 16000
    wf = out["waveform"]
    assert tuple(wf.shape) == (1, 1600)
    assert wf.dtype == torch.float32
    # s16le → [-1, 1): 1000/32768
    assert wf.abs().max().item() == pytest.approx(1000 / 32768.0)


@pytest.mark.parametrize(
    "rate,channels",
    [(44100, 1), (16000, 2)],
)
def test_load_waveform_rejects_non_normalized(tmp_path, rate, channels):
    p = tmp_path / "bad.wav"
    _write_wav(p, rate=rate, channels=channels)

    with pytest.raises(ModelLoadError) as exc:
        _diarizer()._load_waveform(str(p))
    assert "norm_wav_not_16k_mono_s16le" in str(exc.value)


def test_diarize_without_pipeline_raises(tmp_path):
    p = tmp_path / "norm.wav"
    _write_wav(p, rate=16000, channels=1)
    with pytest.raises(ModelLoadError):
        _diarizer().diarize(str(p))
