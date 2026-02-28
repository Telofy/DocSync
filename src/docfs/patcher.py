from __future__ import annotations

from typing import Any

from .diffing import text_edits


def _utf16_units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def utf16_index_from_offset(text: str, offset: int) -> int:
    # Docs document body indexing starts at 1.
    return _utf16_units(text[:offset]) + 1


def build_docs_requests_for_text_change(tab_id: str, remote_text: str, target_text: str) -> list[dict[str, Any]]:
    # Google Docs body content ends with an implicit terminal newline that
    # cannot be deleted. Diff only the mutable prefix before that newline.
    remote_mutable = remote_text[:-1] if remote_text.endswith("\n") else remote_text
    target_mutable = target_text[:-1] if target_text.endswith("\n") else target_text

    edits = text_edits(remote_mutable, target_mutable)
    if not edits:
        return []

    requests: list[dict[str, Any]] = []
    # Descending offsets so earlier requests do not invalidate later indices.
    for edit in sorted(edits, key=lambda e: e.start, reverse=True):
        start_idx = utf16_index_from_offset(remote_mutable, edit.start)
        end_idx = utf16_index_from_offset(remote_mutable, edit.end)

        if edit.tag in {"delete", "replace"} and end_idx > start_idx:
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

        if edit.tag in {"insert", "replace"} and edit.text:
            requests.append(
                {
                    "insertText": {
                        "location": {"tabId": tab_id, "index": start_idx},
                        "text": edit.text,
                    }
                }
            )

    return requests
