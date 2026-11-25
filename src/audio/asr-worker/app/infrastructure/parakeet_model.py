"""Infrastructure: Parakeet TDT 0.6B v3 via `nemo_toolkit` (NeMo ASR).

Weights load as fp16 on CUDA pinned to `ASR_REVISION` (not main, ADR-013). No fallback to
another model or to CPU: a missing/incompatible stack → crash at startup with
`ModelLoadError`. The model detects the language itself (RU/EN); `language_hint` is not used.

Input — 16 kHz mono s16le PCM windows (already normalized `norm.wav`). Loading and inference
are lazy: the heavy `nemo_toolkit` is imported only on the GPU path, unit tests never
touch it.
"""

from __future__ import annotations

import logging

from app.application.ports.asr_model import ModelLoadError
from app.domain.transcription import TranscriptionOutput

logger = logging.getLogger(__name__)

# PCM s16le: 2 bytes per sample, 16000 samples/s → 32000 bytes/s (ADR-014).
_BYTES_PER_MS = 32


def window_byte_range(start_ms: int, end_ms: int) -> tuple[int, int]:
    """`(start_byte, num_bytes)` for the PCM window `[start_ms, end_ms)` without the WAV header.

    The offset is counted from the start of the data chunk (a 44-byte WAV header for
    canonical RIFF). The window is read as is: 2 bytes per s16le sample.
    """
    start_byte = start_ms * _BYTES_PER_MS
    num_bytes = max(0, (end_ms - start_ms) * _BYTES_PER_MS)
    return start_byte, num_bytes


class ParakeetModel:
    def __init__(
        self,
        *,
        model_name: str,
        revision: str,
        device: str,
        hf_home: str,
        use_fp16: bool = True,
        batch_size: int = 8,
    ) -> None:
        self._model_name = model_name
        self._revision = revision
        self._device = device
        self._hf_home = hf_home
        self._use_fp16 = use_fp16
        # Windows per GPU call. A turn window is 1-10 s of audio: on its own it leaves the
        # card idle (measured: 11 % mean utilization, 0.21 s per call mostly overhead).
        # NeMo transcribes a *list* of 1-D waveforms in one pass (`batch_size` pads and
        # stacks them), so the turns of an offline batch share one call.
        self._batch_size = max(1, batch_size)
        self._model = None

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def _load_model(self):
        # Late import: nemo_toolkit + torch are heavy and needed only on the GPU path.
        try:
            import torch  # noqa: PLC0415
            from huggingface_hub import hf_hub_download  # noqa: PLC0415
            from nemo.collections.asr.models import ASRModel  # noqa: PLC0415
        except ImportError as exc:
            raise ModelLoadError("nemo_toolkit/torch is not installed") from exc

        try:
            # NeMo 3.x `ASRModel.from_pretrained` takes no `revision`/`cache_dir` — it
            # resolves the repo's default branch. The revision is the contract (ADR-013:
            # `main` would silently change the text), so the `.nemo` file is fetched here
            # with the pinned commit sha into HF_HOME and restored from the local path.
            model_file = hf_hub_download(
                repo_id=self._model_name,
                filename=f"{self._model_name.rsplit('/', 1)[-1]}.nemo",
                revision=self._revision or None,
                cache_dir=self._hf_home or None,
            )
            model = ASRModel.restore_from(restore_path=model_file)
            if self._use_fp16:
                model = model.half()
            model = model.to(torch.device(self._device))
            model.eval()
        except Exception as exc:  # noqa: BLE001
            raise ModelLoadError("hf_model_load_failed") from exc
        return model

    def load(self) -> None:
        logger.info(
            "asr_model_loading model=%s revision=%s device=%s",
            self._model_name,
            self._revision,
            self._device,
        )
        self._model = self._load_model()
        logger.info("asr_model_loaded")

    def transcribe_windows(
        self,
        windows: list[bytes],
        *,
        seqs: list[int],
        language_hint: str | None = None,
    ) -> TranscriptionOutput:
        """Transcribes windows via NeMo. NeMo detects the language (language_hint is ignored).

        The windows of one call go to the GPU together (up to `batch_size`), not one by one:
        NeMo accepts a list of 1-D waveforms and pads/stacks them internally, restoring the
        input order (`shuffle=False` in its tensor dataloader). On the real 15-minute
        recording (257 windows) this turned 54.1 s into 10.7 s at `batch_size=8` with
        257/257 identical texts, and raised mean GPU utilization from 11 % to 18 %.
        A window is 1-10 s: on its own it does not fill the card, the call is overhead.
        """
        if self._model is None:
            raise ModelLoadError("model is not loaded")
        if not windows:
            return TranscriptionOutput(texts={}, language=None)
        if len(windows) != len(seqs):
            raise ValueError("windows and seqs must be parallel")

        import torch  # noqa: PLC0415

        # PCM s16le -> float32 ([-1, 1]) one-dimensional tensors.
        # NeMo 3.x takes a list of 1-D waveforms: a (1, samples) tensor is rejected with
        # "Input shape mismatch ... expected (batch, time), found (1, 1, N)" (verified
        # on the stand 2026-11-01).
        device = getattr(self._model, "device", None) or torch.device(self._device)
        tensors = [
            (torch.frombuffer(bytearray(raw), dtype=torch.int16).float() / 32768.0).to(device)
            for raw in windows
        ]
        return self._run_chunks(tensors, seqs)

    def _run_chunks(self, tensors: list, seqs: list[int]) -> TranscriptionOutput:
        """One `transcribe()` call per `batch_size` chunks; the order of the input is kept.

        Split out of `transcribe_windows` so the chunking and the seq mapping are testable
        without torch: the tensors are opaque here.
        """
        if self._model is None:
            raise ModelLoadError("model is not loaded")
        texts: dict[int, str] = {}
        language: str | None = None
        for start in range(0, len(tensors), self._batch_size):
            chunk = tensors[start : start + self._batch_size]
            chunk_seqs = seqs[start : start + len(chunk)]
            # One GPU call per chunk; the order of the hypotheses matches the input.
            hyps = self._model.transcribe(chunk, batch_size=len(chunk), verbose=False)
            for seq, hyp in zip(chunk_seqs, hyps, strict=True):
                texts[seq] = (hyp.text if hasattr(hyp, "text") else str(hyp)).strip()
                if language is None:
                    language = getattr(hyp, "language", None)
        return TranscriptionOutput(texts=texts, language=language)

    def transcribe_pcm(self, pcm: bytes) -> tuple[str, str | None]:
        """Transcribes a continuous PCM buffer (16 kHz mono s16le) into full text.

        Used by the note stream (US-05): the buffer grows and the text is overwritten.
        The model detects the language (RU/EN), as with the offline batch.
        """
        if self._model is None:
            raise ModelLoadError("model is not loaded")
        if not pcm:
            return "", None

        import torch  # noqa: PLC0415

        audio = torch.frombuffer(bytearray(pcm), dtype=torch.int16).float() / 32768.0
        hyp = self._model.transcribe([audio.to(self._model.device)])[0]
        text = hyp.text if hasattr(hyp, "text") else str(hyp)
        language = getattr(hyp, "language", None)
        return text.strip(), language
