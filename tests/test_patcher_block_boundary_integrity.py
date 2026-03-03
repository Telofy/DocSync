from __future__ import annotations

from docfs.patcher import build_docs_requests_for_text_change


def _apply_requests_ascii(text: str, requests: list[dict]) -> str:
    out = text
    for req in requests:
        if "deleteContentRange" in req:
            rng = req["deleteContentRange"]["range"]
            start = int(rng["startIndex"]) - 1
            end = int(rng["endIndex"]) - 1
            out = out[:start] + out[end:]
        elif "insertText" in req:
            ins = req["insertText"]
            idx = int(ins["location"]["index"]) - 1
            out = out[:idx] + ins["text"] + out[idx:]
    return out


def test_edit_in_list_item_does_not_merge_into_previous_paragraph() -> None:
    remote = (
        "**How to Use This Book**\n"
        "Explanation of the PwN / PwS signposting system\n"
        "Suggestion: read Part I linearly for orientation, then follow interest or need\n"
    )
    target = (
        "**How to Use This Book**\n"
        "Explanation of the PwN/PwS signposting system\n"
        "Suggestion: read Part I linearly for orientation, then follow interest or need\n"
    )
    requests = build_docs_requests_for_text_change("t.0", remote, target)
    applied = _apply_requests_ascii(remote, requests)
    assert applied == target
