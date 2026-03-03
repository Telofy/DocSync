from __future__ import annotations

from pathlib import Path

from docfs.cli import run_push
from docfs.google_docs import RemoteDocument, RemoteTab
from docfs.ir import Block, BlockKind, DocumentIR
from docfs.state import TabState, WorkspaceState, sha256_text
from docfs.xml_codec import ir_to_xml


class FakeGoogleDocsClient:
    def __init__(self, remote_doc: RemoteDocument) -> None:
        self._remote_doc = remote_doc
        self.batch_calls: list[dict] = []

    def get_document(self, document_id: str) -> RemoteDocument:
        assert document_id == self._remote_doc.document_id
        return self._remote_doc

    def batch_update(self, document_id: str, requests: list[dict], required_revision_id: str | None = None) -> dict:
        self.batch_calls.append(
            {
                "document_id": document_id,
                "requests": requests,
                "required_revision_id": required_revision_id,
            }
        )
        return {}


def test_push_skips_unchanged_xml(monkeypatch, tmp_path: Path) -> None:
    doc = DocumentIR(
        blocks=[
            Block(kind=BlockKind.HEADING, text="Proposed Book Outline: Recovery from Narcissism and Sovereignism", level=2),
            Block(kind=BlockKind.HORIZONTAL_RULE, text=""),
            Block(kind=BlockKind.PARAGRAPH, text="Author Bios"),
            Block(kind=BlockKind.LIST_ITEM, text="Item one", ordered=False, indent=0),
        ]
    )
    xml_content = ir_to_xml(doc)
    file_name = "Contents.xml"
    (tmp_path / file_name).write_text(xml_content, encoding="utf-8")

    remote_text = "Proposed Book Outline: Recovery from Narcissism and Sovereignism\nAuthor Bios\nItem one\n"
    tab_id = "t.0"
    state = WorkspaceState(
        document_id="doc-1",
        document_revision_id="rev-1",
        tabs={
            tab_id: TabState(
                tab_id=tab_id,
                title="Contents",
                file_name=file_name,
                content_sha256=sha256_text(xml_content),
                base_content=xml_content,
                base_remote_text=remote_text,
            )
        },
    )
    state.save(tmp_path)

    remote_doc = RemoteDocument(
        document_id="doc-1",
        revision_id="rev-1",
        tabs=[
            RemoteTab(
                tab_id=tab_id,
                title="Contents",
                plain_text=remote_text,
                ir=DocumentIR(),
                text_chunks=[],
            )
        ],
    )
    fake_client = FakeGoogleDocsClient(remote_doc=remote_doc)

    monkeypatch.setattr("docfs.cli.GoogleDocsClient", lambda: fake_client)

    exit_code = run_push(document_id="doc-1", workspace=tmp_path, force=False, dry_run=False)

    assert exit_code == 0
    assert fake_client.batch_calls == []
