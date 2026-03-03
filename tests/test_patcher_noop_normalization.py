from __future__ import annotations

from docfs.patcher import build_docs_requests_for_text_change


def test_patcher_treats_blank_line_only_deltas_as_noop() -> None:
    remote = (
        "Book Outline: Recovery from Narcissism and Sovereignism\n"
        "A Note on Language and Signposting\n"
        "Throughout this outline, ...\n"
    )
    target = (
        "Book Outline: Recovery from Narcissism and Sovereignism\n\n"
        "A Note on Language and Signposting\n\n"
        "Throughout this outline, ...\n"
    )

    requests = build_docs_requests_for_text_change("t.0", remote, target)
    assert requests == []
