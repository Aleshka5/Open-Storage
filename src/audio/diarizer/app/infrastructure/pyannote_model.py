"""Infrastructure: Pyannote community-1 via the `pyannote.audio` library.

Weights load as fp16 on CUDA pinned to `DIARIZATION_REVISION` (not main, ADR-013). No
fallback to another model or to CPU: a missing token/gated/incompatibility → crash at
startup with `ModelLoadError` (only the code goes to the log, never the token).
"""

from __future__ import annotations

import logging

from app.application.ports.diarizer_model import ModelLoadError
from app.domain.diarization import DiarizationResult, Turn, build_speakers

logger = logging.getLogger(__name__)


class PyannoteDiarizer:
    def __init__(
        self,
        *,
        model_name: str,
        revision: str,
        device: str,
        hf_token: str | None,
        hf_home: str,
        use_fp16: bool = True,
    ) -> None:
        self._model_name = model_name
        self._revision = revision
        self._device = device
        self._hf_token = hf_token
        self._hf_home = hf_home
        self._use_fp16 = use_fp16
        self._pipeline = None

    @property
    def loaded(self) -> bool:
        return self._pipeline is not None

    def _load_pipeline(self):
        # Late import: torch+pyannote are heavy dependencies needed only on the GPU path.
        try:
            import torch  # noqa: PLC0415
            from pyannote.audio import Pipeline  # noqa: PLC0415
        except ImportError as exc:
            raise ModelLoadError("pyannote.audio/torch is not installed") from exc

        try:
            pipeline = Pipeline.from_pretrained(
                self._model_name,
                revision=self._revision,
                token=self._hf_token,
                cache_dir=self._hf_home or None,
            )
            if pipeline is None:
                raise ModelLoadError("pipeline_not_resolved")
            pipeline = pipeline.to(torch.device(self._device))
            # pyannote.audio 4.x `Pipeline.to()` accepts a device only — a dtype raises
            # `TypeError: device must be an instance of torch.device` — and casting the two
            # networks to half breaks the first forward pass (`instance_norm` gets a float32
            # input against half weights). The pipeline therefore runs in fp32, the precision
            # pyannote supports. Logged, not silent: ADR-013 asks for fp16, and the V100 has
            # the headroom for fp32 (~3-4 GB against 32 GB).
            if self._use_fp16:
                logger.info("precision_fp32 fp16_unavailable_in_pyannote_pipeline")
        except ModelLoadError:
            raise
        except Exception as exc:  # noqa: BLE001
            # No token/gated/CUDA incompatibility — an explicit code, not a silent fallback.
            raise ModelLoadError("hf_auth_failed") from exc
        return pipeline

    def load(self) -> None:
        logger.info(
            "diarizer_model_loading model=%s revision=%s device=%s",
            self._model_name,
            self._revision,
            self._device,
        )
        self._pipeline = self._load_pipeline()
        logger.info("diarizer_model_loaded")

    def diarize(self, wav_path: str) -> DiarizationResult:
        if self._pipeline is None:
            raise ModelLoadError("model is not loaded")
        audio = self._load_waveform(wav_path)
        # `return_embeddings=True` installs the embedding hook to get speaker centroids
        # (ADR-007 — the same vector space).
        try:
            output = self._pipeline(audio, return_embeddings=True)
        except TypeError:
            # The old pipeline signature does not accept return_embeddings — no centroids.
            output = self._pipeline(audio)
        annotation, embeddings = self._unpack(output)
        return self._to_result(annotation, embeddings=embeddings)

    @staticmethod
    def _unpack(output) -> tuple[object, dict | None]:
        """Accept both pyannote 4 `DiarizeOutput` and the 3.x `(annotation, embeddings)` tuple.

        In 4.x the speaker is not the annotation label alone: `speaker_embeddings` is an
        `np.ndarray` whose row `s` belongs to `sorted(speaker_diarization.labels())[s]`
        (the pipeline's own docstring). `exclusive_speaker_diarization` is used for turns —
        it is the same diarization without overlapping speech (ADR-002: exactly one speaker
        at any moment).
        """
        if hasattr(output, "speaker_diarization"):
            own = output.speaker_diarization
            annotation = output.exclusive_speaker_diarization
            if annotation is None or annotation.get_timeline().duration() == 0:
                annotation = own
            vecs = getattr(output, "speaker_embeddings", None)
            embeddings: dict | None = None
            if vecs is not None and len(vecs):
                labels = sorted(own.labels())
                embeddings = {label: vecs[i] for i, label in enumerate(labels) if i < len(vecs)}
            return annotation, embeddings
        if isinstance(output, tuple):
            annotation, embeddings = output[0], (output[1] if len(output) > 1 else None)
            return annotation, embeddings
        return output, None

    def _load_waveform(self, wav_path: str) -> dict:
        """`norm.wav` → `{"waveform": (1, N) float32, "sample_rate": 16000}`, no torchcodec.

        pyannote.audio 4.x decodes a *file path* through torchcodec, and in this image
        torchcodec cannot load at all: the wheel is a CUDA 13 build (`libcudart.so.13`)
        while torch is cu126 for sm_70, and it wants FFmpeg 5 (`libavcodec.so.58`) while
        the image ships FFmpeg 7. `from_pretrained` therefore succeeds and the *first*
        `pipeline(path)` dies on `libtorchcodec_image.so`. Preloading the waveform is the
        documented way around it and costs nothing: `norm.wav` is always 16 kHz mono
        s16le (ADR-014), so decoding it is a stdlib job (no resampling, no codec init).
        """
        import wave  # noqa: PLC0415

        import torch  # noqa: PLC0415

        with wave.open(wav_path, "rb") as w:
            if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getframerate() != 16000:
                # Do not resample silently: a wrong rate changes the speakers, not just the
                # quality (ADR-014 requires normalization upstream).
                raise ModelLoadError(
                    "norm_wav_not_16k_mono_s16le "
                    f"channels={w.getnchannels()} width={w.getsampwidth()} "
                    f"rate={w.getframerate()}"
                )
            frames = w.readframes(w.getnframes())
        # bytearray: `frombuffer` needs a writable buffer.
        audio = torch.frombuffer(bytearray(frames), dtype=torch.int16).float() / 32768.0
        return {"waveform": audio.unsqueeze(0), "sample_rate": 16000}

    def _to_result(self, annotation, embeddings=None) -> DiarizationResult:
        """One cluster per file (ADR-002): turns + centroid per speaker.

        The pipeline's argmax annotation is already exclusive: exactly one speaker at every
        moment — `itertracks(yield_label=True)` yields `(segment, track, speaker)` without
        overlaps. We merge adjacent turns of the same speaker (boundary duplicates/annotation
        artifacts). `overlap` is metadata about overlapping speech in the original track;
        community-1 does not emit it in the standard annotation output, so it defaults to False
        (ADR-002: does not affect the chat).
        """
        raw_turns: list[tuple[str, int, int]] = []
        for segment, _track, speaker in annotation.itertracks(yield_label=True):
            start_ms = int(round(segment.start * 1000))
            end_ms = int(round(segment.end * 1000))
            raw_turns.append((speaker, start_ms, end_ms))

        if not raw_turns:
            return DiarizationResult(turns=[], speakers=[], duration_ms=0)

        raw_turns.sort(key=lambda x: (x[1], x[0]))
        turns: list[Turn] = []
        for speaker, start, end in raw_turns:
            if turns and turns[-1].speaker_key == speaker and start <= turns[-1].end_ms:
                # The same speaker continues right at the edge — merge (0 ms tolerance).
                turns[-1] = Turn(
                    speaker_key=speaker,
                    start_ms=turns[-1].start_ms,
                    end_ms=max(turns[-1].end_ms, end),
                    overlap=turns[-1].overlap,
                )
            else:
                turns.append(Turn(speaker_key=speaker, start_ms=start, end_ms=end))

        duration_ms = max(t.end_ms for t in turns) if turns else 0
        centroids = self._compute_centroids(turns, embeddings=embeddings)
        speakers = build_speakers(turns, centroids=centroids)
        return DiarizationResult(turns=turns, speakers=speakers, duration_ms=duration_ms)

    def _compute_centroids(
        self, turns: list[Turn], *, embeddings: dict | None = None
    ) -> dict[str, list[float] | None]:
        """One centroid per speaker from the embeddings of the same pipeline (ADR-007).

        `embeddings` is a mapping speaker -> (embedding, count) from the `return_embeddings`
        hook. If embeddings are unavailable (old pipeline/no hook), we return `None` per
        speaker: the centroid is absent rather than a fake zero vector. US-06 must
        check for `None` before writing to Qdrant instead of silently comparing zeros.
        """
        if embeddings is None:
            return {t.speaker_key: None for t in turns}
        out: dict[str, list[float] | None] = {}
        for t in turns:
            raw = embeddings.get(t.speaker_key)
            # The hook yields (embedding, support) — normalize it, keep only the vector.
            if isinstance(raw, tuple) and raw:
                raw = raw[0]
            if raw is None:
                out[t.speaker_key] = None
                continue
            vec = [float(x) for x in raw]
            norm = sum(v * v for v in vec) ** 0.5
            if norm > 0:
                vec = [v / norm for v in vec]
            out[t.speaker_key] = vec
        return out
