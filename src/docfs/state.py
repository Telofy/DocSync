from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


STATE_FILE = ".docsync_state.json"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class TabState:
    tab_id: str
    title: str
    file_name: str
    markdown_sha256: str
    base_markdown: str
    base_remote_text: str


@dataclass(slots=True)
class WorkspaceState:
    document_id: str
    document_revision_id: str | None
    tabs: dict[str, TabState] = field(default_factory=dict)

    @staticmethod
    def path(workspace: Path) -> Path:
        return workspace / STATE_FILE

    @classmethod
    def load(cls, workspace: Path) -> WorkspaceState:
        p = cls.path(workspace)
        if not p.exists():
            raise FileNotFoundError(f"Missing state file: {p}")
        raw = json.loads(p.read_text(encoding="utf-8"))
        tabs = {
            tab_id: TabState(**payload)
            for tab_id, payload in raw.get("tabs", {}).items()
        }
        return WorkspaceState(
            document_id=raw["document_id"],
            document_revision_id=raw.get("document_revision_id"),
            tabs=tabs,
        )

    def save(self, workspace: Path) -> None:
        payload = {
            "document_id": self.document_id,
            "document_revision_id": self.document_revision_id,
            "tabs": {tab_id: asdict(tab) for tab_id, tab in self.tabs.items()},
        }
        self.path(workspace).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
