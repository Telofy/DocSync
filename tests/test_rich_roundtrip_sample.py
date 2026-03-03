from __future__ import annotations

from docfs.google_docs import tab_to_ir
from docfs.markdown_codec import ir_to_docs_projection, ir_to_markdown, markdown_to_ir


def _docs_tab_from_lines(lines: list[tuple[str, str, dict]], include_hr: bool = True) -> dict:
    """
    Build a lightweight Docs-like tab payload.
    Tuple format: (kind, content, textStyle)
      - kind: heading3 | paragraph | bullet
    """
    content: list[dict] = []
    for kind, text, text_style in lines:
        named = "NORMAL_TEXT"
        paragraph: dict = {"elements": [], "paragraphStyle": {}}
        if kind == "heading3":
            named = "HEADING_3"
        paragraph["paragraphStyle"]["namedStyleType"] = named
        if kind == "bullet":
            paragraph["bullet"] = {"nestingLevel": 0}
        paragraph["elements"].append({"textRun": {"content": text + "\n", "textStyle": text_style}})
        content.append({"paragraph": paragraph})
    if include_hr:
        content.append(
            {
                "paragraph": {
                    "elements": [{"horizontalRule": {}}],
                    "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                }
            }
        )
    return {"documentTab": {"body": {"content": content}}}


def test_rich_markdown_sample_roundtrip_projection_equivalence() -> None:
    tab = _docs_tab_from_lines(
        [
            ("heading3", "Front Matter", {}),
            ("paragraph", "Short Glossary of Essential Terms", {"bold": True}),
            (
                "bullet",
                "Concise definitions (~1 paragraph each) of: pathological narcissism, sovereignism, core shame",
                {},
            ),
            ("bullet", "Full glossary at back of book", {}),
        ]
    )

    # Pull side: Docs JSON -> IR -> Markdown.
    pulled_markdown = ir_to_markdown(tab_to_ir(tab))

    # Push side projection from Markdown.
    projected = ir_to_docs_projection(markdown_to_ir(pulled_markdown)).text

    # Expected plain text close to Docs extraction semantics.
    expected_plain = (
        "Front Matter\n"
        "Short Glossary of Essential Terms\n"
        "Concise definitions (~1 paragraph each) of: pathological narcissism, sovereignism, core shame\n"
        "Full glossary at back of book\n"
    )
    assert projected == expected_plain
