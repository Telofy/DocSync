from __future__ import annotations
# pyright: reportMissingImports=false

from dataclasses import dataclass
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


def tab_plain_text(tab: dict[str, Any]) -> str:
    body = tab.get("documentTab", {}).get("body", {})
    text = _extract_text_from_structural_elements(body.get("content", []))
    if not text.endswith("\n"):
        text += "\n"
    return text


def tab_to_ir(tab: dict[str, Any]) -> DocumentIR:
    body = tab.get("documentTab", {}).get("body", {})
    blocks: list[Block] = []
    for element in body.get("content", []):
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        line = ""
        for pe in paragraph.get("elements", []):
            text_run = pe.get("textRun")
            if text_run:
                line += text_run.get("content", "")
        line = line.rstrip("\n")
        style = paragraph.get("paragraphStyle", {})
        named = style.get("namedStyleType", "NORMAL_TEXT")
        if named.startswith("HEADING_"):
            maybe_level = named.split("_")[-1]
            level = int(maybe_level) if maybe_level.isdigit() else 1
            blocks.append(Block(kind=BlockKind.HEADING, text=line, level=level))
        elif paragraph.get("bullet"):
            bullet = paragraph.get("bullet", {})
            # Preserve nested list depth from Google Docs -> Markdown indentation.
            nesting = bullet.get("nestingLevel", 0)
            indent = nesting if isinstance(nesting, int) and nesting > 0 else 0
            blocks.append(
                Block(
                    kind=BlockKind.LIST_ITEM,
                    text=line,
                    ordered=False,
                    indent=indent,
                )
            )
        else:
            blocks.append(Block(kind=BlockKind.PARAGRAPH, text=line))
    return DocumentIR(blocks=blocks)


@dataclass(slots=True)
class RemoteTab:
    tab_id: str
    title: str
    plain_text: str
    ir: DocumentIR


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
