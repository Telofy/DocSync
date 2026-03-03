from __future__ import annotations

from docfs.patcher import build_docs_requests_for_text_change


def test_single_text_edit_ignores_unrelated_blank_line_diffs() -> None:
    remote = (
        "Header\n\n"
        "Explanation of the PwN / PwS signposting system\n"
        "Tail\n"
    )
    target = (
        "Header\n"
        "Explanation of the PwN/PwS signposting system\n"
        "Tail\n"
    )
    requests = build_docs_requests_for_text_change("t.0", remote, target)

    # One line replacement should result in exactly one delete + one insert.
    assert len(requests) == 2
    assert "deleteContentRange" in requests[0]
    assert "insertText" in requests[1]
