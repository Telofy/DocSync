from __future__ import annotations
# pyright: reportMissingImports=false

from dataclasses import dataclass
import json
from typing import Any

from .ir import Block, BlockKind, DocumentIR


def flatten_tabs(tabs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    stack: list[dict[str, Any]] = list(reversed(tabs))
    while stack:
        tab = stack.pop()
        out.append(tab)
        children = tab.get("childTabs", [])
        for child in reversed(children):
            stack.append(child)
    return out


def _extract_text_from_structural_elements(elements: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for element in elements:
        paragraph = element.get("paragraph")
        if paragraph:
            for pe in paragraph.get("elements", []):
                text_run = pe.get("textRun")
                if text_run and "content" in text_run:
                    chunks.append(text_run["content"])
            continue
        table = element.get("table")
        if table:
            for row in table.get("tableRows", []):
                for cell in row.get("tableCells", []):
                    chunks.append(_extract_text_from_structural_elements(cell.get("content", [])))
            continue
        toc = element.get("tableOfContents")
        if toc:
            chunks.append(_extract_text_from_structural_elements(toc.get("content", [])))
    return "".join(chunks)


@dataclass(slots=True)
class TextChunk:
    plain_start: int
    plain_end: int
    doc_start: int
    doc_end: int
    text: str


def _extract_text_and_chunks_from_structural_elements(
    elements: list[dict[str, Any]],
    chunks: list[TextChunk],
    plain_offset: int = 0,
) -> tuple[str, int]:
    parts: list[str] = []
    offset = plain_offset
    for element in elements:
        paragraph = element.get("paragraph")
        if paragraph:
            for pe in paragraph.get("elements", []):
                text_run = pe.get("textRun")
                if text_run and "content" in text_run:
                    content = text_run["content"]
                    parts.append(content)
                    start_index = pe.get("startIndex")
                    end_index = pe.get("endIndex")
                    if isinstance(start_index, int) and isinstance(end_index, int) and content:
                        chunks.append(
                            TextChunk(
                                plain_start=offset,
                                plain_end=offset + len(content),
                                doc_start=start_index,
                                doc_end=end_index,
                                text=content,
                            )
                        )
                    offset += len(content)
            continue

        table = element.get("table")
        if table:
            for row in table.get("tableRows", []):
                for cell in row.get("tableCells", []):
                    cell_text, offset = _extract_text_and_chunks_from_structural_elements(
                        cell.get("content", []),
                        chunks,
                        offset,
                    )
                    parts.append(cell_text)
            continue

        toc = element.get("tableOfContents")
        if toc:
            toc_text, offset = _extract_text_and_chunks_from_structural_elements(
                toc.get("content", []),
                chunks,
                offset,
            )
            parts.append(toc_text)
    return "".join(parts), offset


def tab_plain_text(tab: dict[str, Any]) -> str:
    body = tab.get("documentTab", {}).get("body", {})
    text = _extract_text_from_structural_elements(body.get("content", []))
    if not text.endswith("\n"):
        text += "\n"
    return text


def tab_text_chunks(tab: dict[str, Any]) -> list[TextChunk]:
    body = tab.get("documentTab", {}).get("body", {})
    chunks: list[TextChunk] = []
    _extract_text_and_chunks_from_structural_elements(body.get("content", []), chunks, 0)
    return chunks


def _apply_markdown_style_markers(text: str, style: dict[str, Any]) -> str:
    if not text:
        return text
    out = text
    if style.get("code"):
        out = f"`{out}`"
    if style.get("bold"):
        out = f"**{out}**"
    if style.get("italic"):
        out = f"*{out}*"
    return out


def _paragraph_to_markdown_line(paragraph: dict[str, Any]) -> str:
    parts: list[str] = []
    for pe in paragraph.get("elements", []):
        text_run = pe.get("textRun")
        if not text_run:
            continue
        content = text_run.get("content", "")
        if not content:
            continue
        content = content.rstrip("\n")
        if not content:
            continue
        text_style = text_run.get("textStyle", {})
        parts.append(_apply_markdown_style_markers(content, text_style))
    return "".join(parts)


def _paragraph_has_horizontal_rule(paragraph: dict[str, Any]) -> bool:
    for pe in paragraph.get("elements", []):
        if pe.get("horizontalRule") is not None:
            return True
    return False


def _paragraph_to_block(paragraph: dict[str, Any]) -> Block:
    if _paragraph_has_horizontal_rule(paragraph):
        return Block(kind=BlockKind.HORIZONTAL_RULE, text="")

    line = _paragraph_to_markdown_line(paragraph)
    style = paragraph.get("paragraphStyle", {})
    named = style.get("namedStyleType", "NORMAL_TEXT")
    if named.startswith("HEADING_"):
        maybe_level = named.split("_")[-1]
        level = int(maybe_level) if maybe_level.isdigit() else 1
        return Block(kind=BlockKind.HEADING, text=line, level=level)
    elif paragraph.get("bullet"):
        bullet = paragraph.get("bullet", {})
        # Preserve nested list depth from Google Docs -> Markdown indentation.
        nesting = bullet.get("nestingLevel", 0)
        indent = nesting if isinstance(nesting, int) and nesting > 0 else 0
        return Block(
            kind=BlockKind.LIST_ITEM,
            text=line,
            ordered=False,
            indent=indent,
        )
    return Block(kind=BlockKind.PARAGRAPH, text=line)


def _blocks_from_structural_elements(elements: list[dict[str, Any]]) -> list[Block]:
    blocks: list[Block] = []
    for element in elements:
        paragraph = element.get("paragraph")
        if paragraph:
            blocks.append(_paragraph_to_block(paragraph))
            continue

        table = element.get("table")
        if table:
            for row in table.get("tableRows", []):
                for cell in row.get("tableCells", []):
                    blocks.extend(_blocks_from_structural_elements(cell.get("content", [])))
            continue

        toc = element.get("tableOfContents")
        if toc:
            blocks.extend(_blocks_from_structural_elements(toc.get("content", [])))
            continue

    return blocks


def tab_to_ir(tab: dict[str, Any]) -> DocumentIR:
    body = tab.get("documentTab", {}).get("body", {})
    blocks = _blocks_from_structural_elements(body.get("content", []))
    return DocumentIR(blocks=blocks)


@dataclass(slots=True)
class RemoteTab:
    tab_id: str
    title: str
    plain_text: str
    ir: DocumentIR
    text_chunks: list[TextChunk]


@dataclass(slots=True)
class RemoteDocument:
    document_id: str
    revision_id: str | None
    tabs: list[RemoteTab]


class GoogleDocsClient:
    def __init__(self) -> None:
        try:
            from googleapiclient.discovery import build
            import google.auth
        except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "Google client libraries are required. Install dependencies with `poetry install`."
            ) from exc
        scopes = ["https://www.googleapis.com/auth/documents"]
        credentials, _ = google.auth.default(scopes=scopes)
        self._service = build("docs", "v1", credentials=credentials, cache_discovery=False)

    def get_document(self, document_id: str) -> RemoteDocument:
        raw = (
            self._service.documents()
            .get(documentId=document_id, includeTabsContent=True, suggestionsViewMode="PREVIEW_WITHOUT_SUGGESTIONS")
            .execute()
        )
        tabs = flatten_tabs(raw.get("tabs", []))
        remote_tabs: list[RemoteTab] = []
        for tab in tabs:
            props = tab.get("tabProperties", {})
            tab_id = props.get("tabId")
            title = props.get("title", tab_id or "untitled")
            if not tab_id:
                continue
            remote_tabs.append(
                RemoteTab(
                    tab_id=tab_id,
                    title=title,
                    plain_text=tab_plain_text(tab),
                    ir=tab_to_ir(tab),
                    text_chunks=tab_text_chunks(tab),
                )
            )
        return RemoteDocument(
            document_id=document_id,
            revision_id=raw.get("revisionId"),
            tabs=remote_tabs,
        )

    def batch_update(
        self,
        document_id: str,
        requests: list[dict[str, Any]],
        required_revision_id: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"requests": requests}
        if required_revision_id:
            body["writeControl"] = {"requiredRevisionId": required_revision_id}
        return self._service.documents().batchUpdate(documentId=document_id, body=body).execute()
