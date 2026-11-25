"""Guard: the owner field name in code must not be a "corrupted" literal.

History: the secret-redaction layer in tool output displayed the real field name
(`owner_<token>_id`) as a guillemet-mangled form. During edits this
displayed text once got into the sources — and all owner queries would have silently
stopped finding documents, while the tests stayed green, because the fakes received
the same corrupted literal.

Rule: the owner field name is the same across the repository and comes from one source
(`app/domain/recording.py` in audio-api). No file may contain a variant with
guillemets (U+00AB / U+00BB) inside the field name.
"""

from __future__ import annotations

import pathlib
import re

SERVICE_ROOT = pathlib.Path(__file__).resolve().parents[1]
SUFFIXES = {".py", ".md", ".ts", ".tsx"}
SKIP_DIRS = {".venv", "node_modules", "dist", "__pycache__", ".git"}

# A corrupted literal — guillemets inside the field name.
CORRUPTED = re.compile(r"owner_\u00ab[^\u00ab\u00bb]*\u00bb_id")
# Canonical field name: owner_<something>_id without guillemets.
CANONICAL = re.compile(r"\bowner_[A-Za-z0-9_]+_id\b")


def _iter_files():
    for path in SERVICE_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        # This file itself describes the corrupted literal (regex/docstring) — not checked.
        if path.name == pathlib.Path(__file__).name:
            continue
        yield path


def test_no_corrupted_owner_field_literal():
    offenders = []
    for path in _iter_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in CORRUPTED.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{path.relative_to(SERVICE_ROOT)}:{line}: {match.group(0)}")
    assert not offenders, (
        "A corrupted owner literal (guillemets inside the field name) — owner queries "
        "will silently stop finding documents:\n" + "\n".join(offenders)
    )


def test_owner_field_name_is_consistent_across_services():
    """The same owner field name in all services — one data contract."""
    names: dict[str, set[str]] = {}
    for path in _iter_files():
        if path.suffix != ".py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        found = set(CANONICAL.findall(text))
        if found:
            names[str(path.relative_to(SERVICE_ROOT))] = found

    assert names, "no owner field name found — the check is meaningless"
    all_names = {n for found in names.values() for n in found}
    assert len(all_names) == 1, (
        "Different owner field names in code: "
        + ", ".join(sorted(all_names))
        + "\nFiles: "
        + "; ".join(f"{f}: {sorted(v)}" for f, v in sorted(names.items()))
    )
