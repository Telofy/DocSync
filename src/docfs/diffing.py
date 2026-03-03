from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal


EditTag = Literal["insert", "delete", "replace"]


@dataclass(slots=True)
class TextEdit:
    tag: EditTag
    start: int
    end: int
    text: str


@dataclass(slots=True)
class RebaseConflict:
    reason: str
    local_edit: TextEdit
    remote_edit: TextEdit


@dataclass(slots=True)
class RebaseResult:
    ok: bool
    merged_text: str
    conflicts: list[RebaseConflict]


def text_edits(source: str, target: str) -> list[TextEdit]:
    if source == target:
        return []

    # Fast-path: trim unchanged prefix/suffix before running SequenceMatcher.
    # This avoids quadratic behavior on very large texts with tiny edits.
    source_len = len(source)
    target_len = len(target)

    prefix = 0
    max_prefix = min(source_len, target_len)
    while prefix < max_prefix and source[prefix] == target[prefix]:
        prefix += 1

    suffix = 0
    max_suffix = min(source_len - prefix, target_len - prefix)
    while suffix < max_suffix and source[source_len - 1 - suffix] == target[target_len - 1 - suffix]:
        suffix += 1

    source_mid_end = source_len - suffix
    target_mid_end = target_len - suffix
    source_mid = source[prefix:source_mid_end]
    target_mid = target[prefix:target_mid_end]

    if source_mid == target_mid:
        return []

    sm = SequenceMatcher(None, source_mid, target_mid, autojunk=False)
    edits: list[TextEdit] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "insert":
            edits.append(
                TextEdit(
                    tag="insert",
                    start=prefix + i1,
                    end=prefix + i1,
                    text=target_mid[j1:j2],
                )
            )
        elif tag == "delete":
            edits.append(TextEdit(tag="delete", start=prefix + i1, end=prefix + i2, text=""))
        elif tag == "replace":
            edits.append(
                TextEdit(
                    tag="replace",
                    start=prefix + i1,
                    end=prefix + i2,
                    text=target_mid[j1:j2],
                )
            )
    return edits


def _ranges_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return max(a_start, b_start) < min(a_end, b_end)


def _apply_edit(text: str, edit: TextEdit) -> str:
    return text[: edit.start] + edit.text + text[edit.end :]


def _apply_edits(text: str, edits: list[TextEdit]) -> str:
    for edit in sorted(edits, key=lambda e: e.start, reverse=True):
        text = _apply_edit(text, edit)
    return text


def _transform_position(pos: int, remote_edits: list[TextEdit]) -> int:
    out = pos
    for e in remote_edits:
        if e.tag == "insert":
            if out >= e.start:
                out += len(e.text)
            continue
        deleted_len = e.end - e.start
        inserted_len = len(e.text)
        if out < e.start:
            continue
        if out >= e.end:
            out += inserted_len - deleted_len
        else:
            out = e.start + inserted_len
    return out


def safe_rebase(base: str, local: str, remote: str) -> RebaseResult:
    local_edits = text_edits(base, local)
    remote_edits = text_edits(base, remote)

    conflicts: list[RebaseConflict] = []
    for le in local_edits:
        local_start = le.start
        local_end = le.end if le.end > le.start else le.start + 1
        for re in remote_edits:
            remote_start = re.start
            remote_end = re.end if re.end > re.start else re.start + 1
            if _ranges_overlap(local_start, local_end, remote_start, remote_end):
                conflicts.append(
                    RebaseConflict(
                        reason="overlapping_edit_range",
                        local_edit=le,
                        remote_edit=re,
                    )
                )

    if conflicts:
        return RebaseResult(ok=False, merged_text=remote, conflicts=conflicts)

    transformed_local: list[TextEdit] = []
    for le in local_edits:
        transformed_local.append(
            TextEdit(
                tag=le.tag,
                start=_transform_position(le.start, remote_edits),
                end=_transform_position(le.end, remote_edits),
                text=le.text,
            )
        )

    merged = _apply_edits(remote, transformed_local)
    return RebaseResult(ok=True, merged_text=merged, conflicts=[])
