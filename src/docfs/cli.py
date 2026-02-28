from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
from dotenv import load_dotenv

from .diffing import safe_rebase
from .google_docs import GoogleDocsClient, RemoteTab
from .markdown_codec import ir_to_docs_projection, ir_to_markdown, markdown_to_ir
from .patcher import build_docs_requests_for_text_change
from .state import TabState, WorkspaceState, sha256_text


def _sanitize_title(title: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", title.strip())
    sanitized = sanitized.strip("._")
    return sanitized or "untitled"


def _unique_file_name(existing: set[str], raw_title: str) -> str:
    base = _sanitize_title(raw_title)
    candidate = f"{base}.md"
    index = 2
    while candidate in existing:
        candidate = f"{base}_{index}.md"
        index += 1
    existing.add(candidate)
    return candidate


@dataclass(slots=True)
class PushConflict:
    tab_id: str
    file_name: str
    reason: str


def run_pull(document_id: str, workspace: Path) -> int:
    client = GoogleDocsClient()
    remote = client.get_document(document_id)

    workspace.mkdir(parents=True, exist_ok=True)
    used_names: set[str] = set()
    state = WorkspaceState(document_id=document_id, document_revision_id=remote.revision_id)

    for tab in remote.tabs:
        file_name = _unique_file_name(used_names, tab.title)
        file_path = workspace / file_name
        markdown = ir_to_markdown(tab.ir)
        file_path.write_text(markdown, encoding="utf-8")
        state.tabs[tab.tab_id] = TabState(
            tab_id=tab.tab_id,
            title=tab.title,
            file_name=file_name,
            markdown_sha256=sha256_text(markdown),
            base_markdown=markdown,
            base_remote_text=tab.plain_text,
        )
        print(f"pulled {tab.title!r} -> {file_name}")

    state.save(workspace)
    print(f"wrote state: {WorkspaceState.path(workspace)}")
    return 0


def _tab_map(tabs: list[RemoteTab]) -> dict[str, RemoteTab]:
    return {tab.tab_id: tab for tab in tabs}


def _build_target_remote_text(local_markdown: str) -> str:
    ir = markdown_to_ir(local_markdown)
    projection = ir_to_docs_projection(ir)
    return projection.text


def _write_conflict_report(workspace: Path, conflicts: list[PushConflict]) -> Path:
    report = workspace / ".docsync_conflicts.json"
    payload = {
        "conflicts": [
            {"tab_id": c.tab_id, "file_name": c.file_name, "reason": c.reason}
            for c in conflicts
        ]
    }
    report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return report


def run_push(document_id: str, workspace: Path, force: bool, dry_run: bool) -> int:
    state = WorkspaceState.load(workspace)
    if state.document_id != document_id:
        raise ValueError(
            f"State file is bound to document {state.document_id!r}, not {document_id!r}"
        )

    client = GoogleDocsClient()
    remote = client.get_document(document_id)

    if not force and state.document_revision_id and remote.revision_id != state.document_revision_id:
        raise RuntimeError(
            "Remote revision changed since last pull. "
            "Run `doc pull` or use `doc push -f`."
        )

    remote_tabs = _tab_map(remote.tabs)
    all_requests: list[dict[str, Any]] = []
    conflicts: list[PushConflict] = []
    updated_tab_state: dict[str, TabState] = {}

    for tab_id, tab_state in state.tabs.items():
        remote_tab = remote_tabs.get(tab_id)
        if not remote_tab:
            conflicts.append(
                PushConflict(
                    tab_id=tab_id,
                    file_name=tab_state.file_name,
                    reason="remote_tab_missing",
                )
            )
            continue

        file_path = workspace / tab_state.file_name
        if not file_path.exists():
            conflicts.append(
                PushConflict(
                    tab_id=tab_id,
                    file_name=tab_state.file_name,
                    reason="local_file_missing",
                )
            )
            continue

        local_markdown = file_path.read_text(encoding="utf-8")
        target_from_local = _build_target_remote_text(local_markdown)
        remote_text = remote_tab.plain_text
        base_text = tab_state.base_remote_text

        if force:
            rebase = safe_rebase(base=base_text, local=target_from_local, remote=remote_text)
            if not rebase.ok:
                conflicts.append(
                    PushConflict(
                        tab_id=tab_id,
                        file_name=tab_state.file_name,
                        reason="unsafe_rebase_overlap",
                    )
                )
                continue
            desired_remote_text = rebase.merged_text
        else:
            desired_remote_text = target_from_local

        requests = build_docs_requests_for_text_change(
            tab_id=tab_id,
            remote_text=remote_text,
            target_text=desired_remote_text,
        )
        if requests:
            all_requests.extend(requests)

        updated_tab_state[tab_id] = TabState(
            tab_id=tab_state.tab_id,
            title=remote_tab.title,
            file_name=tab_state.file_name,
            markdown_sha256=sha256_text(local_markdown),
            base_markdown=local_markdown,
            base_remote_text=desired_remote_text,
        )

    if conflicts:
        report = _write_conflict_report(workspace, conflicts)
        click.echo(f"conflicts detected, report written to {report}", err=True)
        return 2

    if dry_run:
        print(f"dry-run: {len(all_requests)} request(s) would be sent")
        return 0

    if all_requests:
        required_revision_id = None if force else state.document_revision_id
        client.batch_update(
            document_id=document_id,
            requests=all_requests,
            required_revision_id=required_revision_id,
        )
        print(f"applied {len(all_requests)} request(s)")
    else:
        print("no changes to push")

    refreshed = client.get_document(document_id)
    next_state = WorkspaceState(
        document_id=document_id,
        document_revision_id=refreshed.revision_id,
        tabs=updated_tab_state if updated_tab_state else state.tabs,
    )
    next_state.save(workspace)
    return 0


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli() -> None:
    """Google Docs tabs <-> Markdown sync."""
    load_dotenv()


@cli.command()
@click.argument("document_id")
@click.option(
    "--workspace",
    default=".",
    show_default=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory where Markdown files and sync state are stored.",
)
def pull(document_id: str, workspace: Path) -> None:
    """Pull tabs into local Markdown files."""
    try:
        raise SystemExit(run_pull(document_id=document_id, workspace=workspace.resolve()))
    except Exception as exc:  # noqa: BLE001
        raise click.ClickException(str(exc)) from exc


@cli.command()
@click.argument("document_id")
@click.option(
    "--workspace",
    default=".",
    show_default=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory where Markdown files and sync state are stored.",
)
@click.option("-f", "--force", is_flag=True, help="Best-effort safe rebase mode.")
@click.option("--dry-run", is_flag=True, help="Preview push result without writing.")
def push(document_id: str, workspace: Path, force: bool, dry_run: bool) -> None:
    """Push local Markdown changes back to Google Docs."""
    try:
        raise SystemExit(
            run_push(
                document_id=document_id,
                workspace=workspace.resolve(),
                force=force,
                dry_run=dry_run,
            )
        )
    except Exception as exc:  # noqa: BLE001
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":
    cli()


def main() -> None:
    """Console entrypoint used by Poetry script."""
    cli()
