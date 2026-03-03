from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from .ir import Block, BlockKind, DocumentIR
from .markdown_codec import DocsProjection


def ir_to_xml(doc: DocumentIR) -> str:
    root = ET.Element("docsync", {"version": "1"})
    for block in doc.blocks:
        attrs = {"kind": block.kind.value}
        if block.level:
            attrs["level"] = str(block.level)
        if block.indent:
            attrs["indent"] = str(block.indent)
        if block.ordered:
            attrs["ordered"] = "true"
        node = ET.SubElement(root, "block", attrs)
        node.text = block.text
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode") + "\n"


def xml_to_ir(xml_text: str) -> DocumentIR:
    root = ET.fromstring(xml_text)
    if root.tag != "docsync":
        raise ValueError("Root element must be <docsync>.")
    blocks: list[Block] = []
    for block_node in root.findall("block"):
        kind_raw = block_node.get("kind", "").strip()
        if not kind_raw:
            raise ValueError("Each <block> element must have a kind attribute.")
        try:
            kind = BlockKind(kind_raw)
        except ValueError as exc:
            raise ValueError(f"Unsupported block kind: {kind_raw!r}") from exc
        text = block_node.text or ""
        level = int(block_node.get("level", "0") or "0")
        indent = int(block_node.get("indent", "0") or "0")
        ordered = (block_node.get("ordered", "false").lower() == "true")
        blocks.append(
            Block(
                kind=kind,
                text=text,
                level=level,
                ordered=ordered,
                indent=indent,
            )
        )
    return DocumentIR(blocks=blocks)


def ir_to_docs_projection(doc: DocumentIR) -> DocsProjection:
    def strip_inline_markers(text: str) -> str:
        out = text
        out = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", out)
        out = re.sub(r"\*\*([^*]+)\*\*", r"\1", out)
        out = re.sub(r"__([^_]+)__", r"\1", out)
        out = re.sub(r"\*([^*]+)\*", r"\1", out)
        out = re.sub(r"_([^_]+)_", r"\1", out)
        out = re.sub(r"`([^`]+)`", r"\1", out)
        return out

    lines: list[str] = []
    for block in doc.blocks:
        if block.kind == BlockKind.HORIZONTAL_RULE:
            continue
        if block.kind == BlockKind.CODE:
            lines.extend(block.text.split("\n") if block.text else [""])
        else:
            lines.append(strip_inline_markers(block.text))
    if not lines:
        return DocsProjection(text="\n")
    text = "\n".join(lines).rstrip("\n") + "\n"
    return DocsProjection(text=text)
