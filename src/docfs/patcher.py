from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Callable
import re

def _utf16_units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def utf16_index_from_offset(text: str, offset: int) -> int:
    # Docs document body indexing starts at 1.
    return _utf16_units(text[:offset]) + 1


def _normalize_text_for_noop_compare(text: str) -> str:
    # Normalize line endings/trailing whitespace and collapse formatting-only
    # blank-line variance so markdown readability spacing does not trigger
    # massive diffs against Docs plain-text extraction.
    out = text.replace("\r\n", "\n").replace("\r", "\n")
    out = "\n".join(line.rstrip() for line in out.split("\n"))
    out = re.sub(r"\n{2,}", "\n", out)
    if not out.endswith("\n"):
        out += "\n"
    return out


def _line_level_edits(source: str, target: str) -> list[tuple[int, int, str]]:
    """
    Return edits as (start_offset, end_offset, replacement_text) using a
    line-level diff (splitlines keepends) so changed blocks are replaced
    wholesale rather than by tiny character edits.
    """
    source_tokens = source.splitlines(keepends=True)
    target_tokens = target.splitlines(keepends=True)

    src_offsets: list[int] = [0]
    for tok in source_tokens:
        src_offsets.append(src_offsets[-1] + len(tok))

    sm = SequenceMatcher(None, source_tokens, target_tokens, autojunk=False)
    edits: list[tuple[int, int, str]] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        start = src_offsets[i1]
        end = src_offsets[i2]
        source_chunk = "".join(source_tokens[i1:i2])
        replacement = "".join(target_tokens[j1:j2])

        # Ignore formatting-only blank line churn. Docs may represent separator
        # paragraphs differently from local editable files.
        if source_chunk.replace("\n", "").strip() == "" and replacement.replace("\n", "").strip() == "":
            continue

        edits.append((start, end, replacement))
    return edits


def build_docs_requests_for_text_change(
    tab_id: str,
    remote_text: str,
    target_text: str,
    offset_to_doc_index: Callable[[int], int] | None = None,
) -> list[dict[str, Any]]:
    if _normalize_text_for_noop_compare(remote_text) == _normalize_text_for_noop_compare(target_text):
        return []

    # Google Docs body content ends with an implicit terminal newline that
    # cannot be deleted. Diff only the mutable prefix before that newline.
    remote_mutable = remote_text[:-1] if remote_text.endswith("\n") else remote_text
    target_mutable = target_text[:-1] if target_text.endswith("\n") else target_text

    edits = _line_level_edits(remote_mutable, target_mutable)
    if not edits:
        return []

    requests: list[dict[str, Any]] = []

    def map_index(offset: int) -> int:
        if offset_to_doc_index is not None:
            return offset_to_doc_index(offset)
        return utf16_index_from_offset(remote_mutable, offset)

    # Descending offsets so earlier requests do not invalidate later indices.
    for start, end, replacement in sorted(edits, key=lambda e: e[0], reverse=True):
        start_idx = map_index(start)
        end_idx = map_index(end)

        if end_idx > start_idx:
            requests.append(
                {
                    "deleteContentRange": {
                        "range": {
                            "tabId": tab_id,
                            "startIndex": start_idx,
                            "endIndex": end_idx,
                        }
                    }
                }
            )

        if replacement:
            requests.append(
                {
                    "insertText": {
                        "location": {"tabId": tab_id, "index": start_idx},
                        "text": replacement,
                    }
                }
            )

    return requests
