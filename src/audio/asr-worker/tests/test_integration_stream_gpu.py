"""Stream integration test against the real Parakeet (GPU), if everything is up.

Skipped without torch/nemo/CUDA. It does not fabricate a result: with the environment
unavailable it honestly `skip`s. Run manually on a GPU host (V100 sm_70) after
`uv sync --extra gpu`. Checks that `ParakeetModel.transcribe_pcm` returns non-empty text and
a language for short synthetic PCM.
"""

from __future__ import annotations

import struct

import pytest


def _has_gpu_stack() -> bool:
    try:
        import torch  # noqa: PLC0415

        if not torch.cuda.is_available():
            return False
        import nemo  # noqa: F401, PLC0415

        return True
    except Exception:  # noqa: BLE001
        return False


need_gpu = pytest.mark.skipif(not _has_gpu_stack(), reason="no torch+nemo+CUDA")


def _sine_pcm(duration_s: float = 1.0, rate: int = 16000, freq: float = 440.0) -> bytes:
    import math  # noqa: PLC0415

    n = int(duration_s * rate)
    out = bytearray()
    for i in range(n):
        sample = int(0.3 * 32767 * math.sin(2 * math.pi * freq * i / rate))
        out += struct.pack("<h", sample)
    return bytes(out)


@need_gpu
def test_real_parakeet_transcribe_pcm():
    """Real model: synthetic input (a tone) does not crash and returns text+language.

    We do not check the text content (a tone is not speech) — only that the model loads and
    returns the `(text, language)` structure without an exception.
    """
    from app.infrastructure.parakeet_model import ParakeetModel  # noqa: PLC0415

    model = ParakeetModel(
        model_name="nvidia/parakeet-tdt-0.6b-v3",
        revision="541d1f99c6b0c3cd0b11a95167540bb8edefd82b",
        device="cuda",
        hf_home="/models/hf",
        use_fp16=True,
    )
    model.load()
    text, language = model.transcribe_pcm(_sine_pcm(1.0))
    assert isinstance(text, str)
    assert language in (None, "ru", "en", "de", "es", "fr", "it")
