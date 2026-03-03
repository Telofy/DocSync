from __future__ import annotations

from docfs.ir import Block, BlockKind, DocumentIR
from docfs.xml_codec import ir_to_docs_projection, ir_to_xml, xml_to_ir


def test_xml_codec_roundtrip_blocks() -> None:
    original = DocumentIR(
        blocks=[
            Block(kind=BlockKind.HEADING, text="Front Matter", level=3),
            Block(kind=BlockKind.PARAGRAPH, text="Short Glossary of Essential Terms"),
            Block(kind=BlockKind.LIST_ITEM, text="Item one", indent=1),
            Block(kind=BlockKind.HORIZONTAL_RULE, text=""),
        ]
    )
    xml_text = ir_to_xml(original)
    restored = xml_to_ir(xml_text)
    assert restored == original


def test_docs_projection_ignores_horizontal_rule() -> None:
    doc = DocumentIR(
        blocks=[
            Block(kind=BlockKind.PARAGRAPH, text="Line one"),
            Block(kind=BlockKind.HORIZONTAL_RULE, text=""),
            Block(kind=BlockKind.PARAGRAPH, text="Line two"),
        ]
    )
    projection = ir_to_docs_projection(doc).text
    assert projection == "Line one\nLine two\n"


def test_docs_projection_strips_markdown_style_markers() -> None:
    doc = DocumentIR(
        blocks=[
            Block(kind=BlockKind.PARAGRAPH, text="**Bold** and *italic* plus `code`"),
        ]
    )
    projection = ir_to_docs_projection(doc).text
    assert projection == "Bold and italic plus code\n"
