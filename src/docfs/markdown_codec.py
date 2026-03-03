from __future__ import annotations

from dataclasses import dataclass
import re

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
    prev: Block | None = None

    def is_hr(block: Block) -> bool:
        return (
            block.kind == BlockKind.HORIZONTAL_RULE
            or (block.kind == BlockKind.PARAGRAPH and block.text.strip() == "---")
        )

    for block in doc.blocks:
        if prev is not None:
            prev_list = prev.kind == BlockKind.LIST_ITEM
            curr_list = block.kind == BlockKind.LIST_ITEM

            need_blank = False
            if is_hr(prev) or is_hr(block):
                need_blank = True
            elif prev.kind == BlockKind.HEADING or block.kind == BlockKind.HEADING:
                need_blank = True
            elif prev.kind == BlockKind.PARAGRAPH and block.kind == BlockKind.PARAGRAPH:
                need_blank = True
            elif prev.kind == BlockKind.CODE or block.kind == BlockKind.CODE:
                need_blank = True
            elif prev_list and not curr_list:
                need_blank = True

            if need_blank and lines and lines[-1] != "":
                lines.append("")

        if block.kind == BlockKind.HEADING:
            lines.append(f"{'#' * max(1, min(block.level, 6))} {block.text}".rstrip())
        elif block.kind == BlockKind.LIST_ITEM:
            prefix = "1. " if block.ordered else "- "
            lines.append(f"{'  ' * max(block.indent, 0)}{prefix}{block.text}".rstrip())
        elif block.kind == BlockKind.BLOCKQUOTE:
            lines.append(f"> {block.text}".rstrip())
        elif block.kind == BlockKind.HORIZONTAL_RULE:
            lines.append("---")
        elif block.kind == BlockKind.CODE:
            lines.append("```")
            lines.extend(block.text.split("\n") if block.text else [])
            lines.append("```")
        else:
            lines.append(block.text)
        prev = block
    if not lines:
        return "\n"
    return "\n".join(lines).rstrip("\n") + "\n"


def ir_to_docs_projection(doc: DocumentIR) -> DocsProjection:
    """
    Convert IR to plain text payload suitable for Docs text insertion/deletion operations.
    Formatting requests are intentionally out of v1 scope; this keeps diffing stable.
    """
    def strip_inline_markdown(text: str) -> str:
        out = text
        # Convert common inline Markdown syntax to plain text for Docs text diffing.
        out = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", out)
        out = re.sub(r"\*\*([^*]+)\*\*", r"\1", out)
        out = re.sub(r"__([^_]+)__", r"\1", out)
        out = re.sub(r"\*([^*]+)\*", r"\1", out)
        out = re.sub(r"_([^_]+)_", r"\1", out)
        out = re.sub(r"`([^`]+)`", r"\1", out)
        return out

    lines: list[str] = []
    last_was_blank = False
    prev_kind: BlockKind | None = None
    for block in doc.blocks:
        # Horizontal rules are formatting-only in this plain-text projection
        # and should not generate text diffs.
        if block.kind == BlockKind.HORIZONTAL_RULE or (
            block.kind == BlockKind.PARAGRAPH and block.text.strip() == "---"
        ):
            continue

        if block.kind == BlockKind.CODE:
            code_lines = block.text.split("\n") if block.text else [""]
            lines.extend(code_lines)
            last_was_blank = bool(code_lines and code_lines[-1] == "")
        else:
            text = strip_inline_markdown(block.text)
            if text == "":
                # Markdown commonly uses a blank separator after headings; this
                # is syntactic in Markdown but not an explicit blank paragraph
                # in Docs plain text.
                if prev_kind == BlockKind.HEADING:
                    continue
                if not last_was_blank:
                    lines.append("")
                    last_was_blank = True
            else:
                lines.append(text)
                last_was_blank = False
        prev_kind = block.kind

    if not lines:
        return DocsProjection(text="\n")
    text = "\n".join(lines).rstrip("\n") + "\n"
    return DocsProjection(text=text)
