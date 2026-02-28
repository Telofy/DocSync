from __future__ import annotations

from dataclasses import dataclass

from .ir import Block, BlockKind, DocumentIR


@dataclass(slots=True)
class DocsProjection:
    text: str


def markdown_to_ir(markdown: str) -> DocumentIR:
    blocks: list[Block] = []
    in_code = False
    code_buf: list[str] = []

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                blocks.append(Block(kind=BlockKind.CODE, text="\n".join(code_buf)))
                code_buf = []
                in_code = False
            else:
                in_code = True
            continue

        if in_code:
            code_buf.append(line)
            continue

        if not stripped:
            blocks.append(Block(kind=BlockKind.PARAGRAPH, text=""))
            continue

        if stripped.startswith("#"):
            hashes = len(stripped) - len(stripped.lstrip("#"))
            heading_text = stripped[hashes:].strip()
            blocks.append(
                Block(
                    kind=BlockKind.HEADING,
                    text=heading_text,
                    level=max(1, min(hashes, 6)),
                )
            )
            continue

        if stripped.startswith("> "):
            blocks.append(Block(kind=BlockKind.BLOCKQUOTE, text=stripped[2:]))
            continue

        if stripped.startswith("- ") or stripped.startswith("* "):
            indent = (len(line) - len(line.lstrip(" "))) // 2
            blocks.append(
                Block(
                    kind=BlockKind.LIST_ITEM,
                    text=stripped[2:],
                    ordered=False,
                    indent=max(indent, 0),
                )
            )
            continue

        parts = stripped.split(". ", 1)
        if len(parts) == 2 and parts[0].isdigit():
            indent = (len(line) - len(line.lstrip(" "))) // 2
            blocks.append(
                Block(
                    kind=BlockKind.LIST_ITEM,
                    text=parts[1],
                    ordered=True,
                    indent=max(indent, 0),
                )
            )
            continue

        blocks.append(Block(kind=BlockKind.PARAGRAPH, text=line))

    if in_code:
        blocks.append(Block(kind=BlockKind.CODE, text="\n".join(code_buf)))

    return DocumentIR(blocks=blocks)


def ir_to_markdown(doc: DocumentIR) -> str:
    lines: list[str] = []
    for block in doc.blocks:
        if block.kind == BlockKind.HEADING:
            lines.append(f"{'#' * max(1, min(block.level, 6))} {block.text}".rstrip())
        elif block.kind == BlockKind.LIST_ITEM:
            prefix = "1. " if block.ordered else "- "
            lines.append(f"{'  ' * max(block.indent, 0)}{prefix}{block.text}".rstrip())
        elif block.kind == BlockKind.BLOCKQUOTE:
            lines.append(f"> {block.text}".rstrip())
        elif block.kind == BlockKind.CODE:
            lines.append("```")
            lines.extend(block.text.split("\n") if block.text else [])
            lines.append("```")
        else:
            lines.append(block.text)
    if not lines:
        return "\n"
    return "\n".join(lines).rstrip("\n") + "\n"


def ir_to_docs_projection(doc: DocumentIR) -> DocsProjection:
    """
    Convert IR to plain text payload suitable for Docs text insertion/deletion operations.
    Formatting requests are intentionally out of v1 scope; this keeps diffing stable.
    """
    lines: list[str] = []
    for block in doc.blocks:
        if block.kind == BlockKind.CODE:
            lines.extend(block.text.split("\n") if block.text else [""])
        else:
            lines.append(block.text)
    text = "\n".join(lines).rstrip("\n") + "\n"
    return DocsProjection(text=text)
