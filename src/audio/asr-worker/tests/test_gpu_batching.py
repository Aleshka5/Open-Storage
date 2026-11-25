"""S-07: the windows of one batch go to the GPU in one call, in the input order.

No torch, no GPU: `_run_chunks` takes the tensors as opaque items, so the chunking and the
seq mapping are checked against a counting fake.
"""

from __future__ import annotations

from app.infrastructure.parakeet_model import ParakeetModel


class FakeInner:
    """Stands in for the NeMo model: one text per input, counts the calls."""

    device = "cuda"

    def __init__(self) -> None:
        self.calls: list[int] = []
        self.batch_sizes: list[int | None] = []

    def transcribe(self, audio, *, batch_size=None, verbose=None) -> list:  # noqa: ANN001, ARG002
        self.calls.append(len(audio))
        self.batch_sizes.append(batch_size)
        return [f"text-{item}" for item in audio]


def make_model(batch_size: int) -> tuple[ParakeetModel, FakeInner]:
    model = ParakeetModel(
        model_name="nvidia/parakeet-tdt-0.6b-v3",
        revision="deadbeef",
        device="cuda",
        hf_home="/models/hf",
        batch_size=batch_size,
    )
    inner = FakeInner()
    model._model = inner
    return model, inner


def test_eight_windows_take_one_call():
    model, inner = make_model(batch_size=8)

    out = model._run_chunks([f"w{i}" for i in range(8)], seqs=list(range(1, 9)))

    assert inner.calls == [8]  # one GPU call, not eight
    assert inner.batch_sizes == [8]
    assert out.texts == {i: f"text-w{i - 1}" for i in range(1, 9)}


def test_more_windows_than_batch_size_are_chunked_in_order():
    model, inner = make_model(batch_size=8)

    out = model._run_chunks([f"w{i}" for i in range(20)], seqs=list(range(1, 21)))

    assert inner.calls == [8, 8, 4]  # tail chunk is not padded up to the full size
    # The order of the input survives the chunking: seq -> its own window.
    assert out.texts[1] == "text-w0"
    assert out.texts[9] == "text-w8"
    assert out.texts[20] == "text-w19"


def test_seqs_are_mapped_not_positional():
    model, _ = make_model(batch_size=4)

    # Turns arrive sorted by start_ms but their `seq` is the ordinal in the recording.
    out = model._run_chunks(["a", "b", "c"], seqs=[7, 3, 11])

    assert out.texts == {7: "text-a", 3: "text-b", 11: "text-c"}


def test_batch_size_one_keeps_the_old_behaviour():
    model, inner = make_model(batch_size=1)

    out = model._run_chunks(["a", "b"], seqs=[1, 2])

    assert inner.calls == [1, 1]
    assert out.texts == {1: "text-a", 2: "text-b"}


def test_hypothesis_objects_are_unwrapped():
    class Hyp:
        def __init__(self, text: str) -> None:
            self.text = text

    class InnerHyps(FakeInner):
        def transcribe(self, audio, *, batch_size=None, verbose=None) -> list:  # noqa: ANN001, ARG002
            return [Hyp(f" {item} ") for item in audio]

    model, _ = make_model(batch_size=2)
    model._model = InnerHyps()

    out = model._run_chunks(["a", "b"], seqs=[1, 2])

    assert out.texts == {1: "a", 2: "b"}  # trimmed, like the per-window loop did
