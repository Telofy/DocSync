from __future__ import annotations

from docfs.patcher import build_docs_requests_for_text_change


def _apply_requests_ascii(text: str, requests: list[dict]) -> str:
    """
    Apply generated requests to ASCII text for regression testing.
    ASCII keeps UTF-16 index math identical to code-point offsets.
    """
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


def test_line_level_patch_handles_small_inline_edit_without_corruption() -> None:
    remote = "PwN / PwS"
    target = "PwN/PwS"
    requests = build_docs_requests_for_text_change("t.0", remote, target)
    applied = _apply_requests_ascii(remote, requests)
    assert applied == target
