"""Infrastructure: note voice embedding via the diarization model (ADR-007).

The note's voice vector **must** live in the same space as the speaker centroids: otherwise
the cosine in suggestions is a number, not a similarity. So we take the embedding model of the
same `speaker-diarization-community-1` pipeline (pinned by `DIARIZATION_REVISION`, ADR-013) and
compute **one** vector over the whole file: the model accepts a long signal by itself, and that
is the best available voice sample (queue-audio-embedding/message.md, item 2).

Without weights/token — `ModelLoadError` at startup, no silent fallback to a foreign model
(ADR-013). The token, phrase texts and object keys never reach the log.
"""

from __future__ import annotations

import logging

from app.application.ports.diarizer_model import ModelLoadError
from app.application.ports.embedding_model import EmbeddingError

logger = logging.getLogger(__name__)

# Model family identifier in `recordings.voice_embedding_model`.
EMBEDDING_MODEL_FAMILY = "pyannote/embedding"


class PyannoteEmbedder:
    """`pyannote/embedding` (WeSpeaker) with the weights of the same diarization pipeline."""

    def __init__(
        self,
        *,
        pipeline_model: str,
        revision: str,
        device: str,
        hf_token: str | None,
        hf_home: str,
        use_fp16: bool = True,
    ) -> None:
        self._pipeline_model = pipeline_model
        self._revision = revision
        self._device = device
        self._hf_token = hf_token
        self._hf_home = hf_home
        self._use_fp16 = use_fp16
        self._inference = None
        self._source = None

    @property
    def loaded(self) -> bool:
        return self._inference is not None

    @property
    def model_id(self) -> str:
        """String in `voice_embedding_model`: model + revision (a change = a new collection)."""
        return f"{EMBEDDING_MODEL_FAMILY}@{self._revision}"

    def load(self) -> None:
        """Extracts the embedding model from the diarization pipeline (same space)."""
        try:
            import torch  # noqa: PLC0415
            from pyannote.audio import Model  # noqa: PLC0415
            from pyannote.audio.pipelines import SpeakerDiarization  # noqa: PLC0415
        except ImportError as exc:
            raise ModelLoadError("pyannote.audio/torch is not installed") from exc

        logger.info(
            "embedding_model_loading model=%s revision=%s device=%s",
            EMBEDDING_MODEL_FAMILY,
            self._revision,
            self._device,
        )
        try:
            pipeline = SpeakerDiarization.from_pretrained(
                self._pipeline_model,
                revision=self._revision,
                # `use_auth_token` was removed from huggingface_hub 1.x — it is `token` now,
                # and passing the old name is a TypeError, not a warning.
                token=self._hf_token,
                cache_dir=self._hf_home or None,
            )
            # `pipeline.embedding` is a dict of params, not a model; the live object is
            # `pipeline._embedding` (a `PyannoteAudioPretrainedSpeakerEmbedding` wrapper whose
            # `__call__` expects a different input layout than our (1, samples) tensor, and
            # which crashes inside kaldi fbank). Its `.model_` is the WeSpeaker net itself and
            # takes (batch, 1, samples) — the same weights the centroids come from
            # (ADR-007: one vector space).
            instance = getattr(pipeline, "_embedding", None)
            dim = getattr(instance, "dimension", None)
            if instance is not None and hasattr(instance, "model_"):
                net = instance.model_
            else:
                # Pipeline without a built-in model — take the same family separately, but
                # with the same pipeline revision (the vector space does not change silently).
                net = Model.from_pretrained(
                    EMBEDDING_MODEL_FAMILY,
                    revision=getattr(pipeline, "embedding_revision", None) or self._revision,
                    token=self._hf_token,
                    cache_dir=self._hf_home or None,
                )
            # Always fp32: the pipeline that produces the centroids runs fp32 (pyannote 4.x
            # has no dtype support in `to()`), and a half-precision note vector would be a
            # different vector space under the same collection (ADR-007).
            if self._use_fp16:
                logger.info("precision_fp32 fp16_unavailable_in_pyannote_embedding")
            self._source = pipeline
            self._inference = net.to(torch.device(self._device))
            self._inference.eval()
            # The model output dimension must match the collection (ADR-007).
            if isinstance(dim, int) and dim != 0:
                from app.domain.diarization import CENTROID_DIM  # noqa: PLC0415

                if dim != CENTROID_DIM:
                    logger.warning(
                        "embedding_model_dim_mismatch model_dim=%d expected=%d", dim, CENTROID_DIM
                    )
        except ModelLoadError:
            raise
        except Exception as exc:  # noqa: BLE001
            # No token/gated/CUDA incompatibility — an explicit code, not a silent fallback.
            raise ModelLoadError("hf_auth_failed") from exc
        logger.info("embedding_model_loaded")

    def embed(self, wav_path: str) -> list[float]:
        """One normalized vector over the whole file."""
        if self._inference is None:
            raise ModelLoadError("embedding model is not loaded")
        import wave  # noqa: PLC0415

        import numpy as np  # noqa: PLC0415
        import torch  # noqa: PLC0415

        # `torchaudio.load` is not usable here: from 2.9 it decodes through torchcodec, which
        # cannot load in this image (CUDA 13 wheel + FFmpeg 5 against cu126 + FFmpeg 7). The
        # input is always `norm.wav` — 16 kHz mono s16le (ADR-014) — so stdlib is enough.
        try:
            with wave.open(wav_path, "rb") as w:
                if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getframerate() != 16000:
                    raise EmbeddingError("decode_failed")
                frames = w.readframes(w.getnframes())
        except EmbeddingError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise EmbeddingError("decode_failed") from exc
        waveform = torch.frombuffer(bytearray(frames), dtype=torch.int16).float() / 32768.0
        # (1, samples) → (batch=1, channel=1, samples): what WeSpeakerResNet34.forward takes.
        waveform = waveform.unsqueeze(0).unsqueeze(0).to(torch.device(self._device))
        with torch.inference_mode():
            raw = self._inference(waveform)
        if isinstance(raw, torch.Tensor):
            raw = raw.detach().float().cpu().numpy()
        vec = np.asarray(raw, dtype="float32").reshape(-1)
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec = vec / norm
        return [float(v) for v in vec]
