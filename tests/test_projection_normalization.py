from __future__ import annotations

from docfs.markdown_codec import ir_to_docs_projection, markdown_to_ir


def test_docs_projection_ignores_hr_and_blank_separators() -> None:
    markdown = "### Front Matter\n\n---\n\nParagraph\n"
    projection = ir_to_docs_projection(markdown_to_ir(markdown))
    assert projection.text == "Front Matter\nParagraph\n"


def test_docs_projection_strips_inline_markdown_markers() -> None:
    markdown = "**Short Glossary of Essential Terms**\n"
    projection = ir_to_docs_projection(markdown_to_ir(markdown))
    assert projection.text == "Short Glossary of Essential Terms\n"


def test_docs_projection_preserves_explicit_blank_paragraph() -> None:
    markdown = "Line one\n\nLine two\n"
    projection = ir_to_docs_projection(markdown_to_ir(markdown))
    assert projection.text == "Line one\n\nLine two\n"
