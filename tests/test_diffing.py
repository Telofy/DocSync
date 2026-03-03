from __future__ import annotations

from docfs.diffing import text_edits


def test_text_edits_returns_single_localized_replace() -> None:
    source = "A" * 5000 + "old" + "Z" * 5000
    target = "A" * 5000 + "new" + "Z" * 5000

    edits = text_edits(source, target)

    assert len(edits) == 1
    edit = edits[0]
    assert edit.tag == "replace"
    assert edit.start == 5000
    assert edit.end == 5003
    assert edit.text == "new"


def test_text_edits_insert_keeps_global_offsets() -> None:
    source = "prefix" + "suffix"
    target = "prefix" + "MID" + "suffix"

    edits = text_edits(source, target)

    assert len(edits) == 1
    edit = edits[0]
    assert edit.tag == "insert"
    assert edit.start == len("prefix")
    assert edit.end == len("prefix")
    assert edit.text == "MID"
