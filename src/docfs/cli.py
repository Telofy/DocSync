from __future__ import annotations

import json
import re
import signal
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import click
from dotenv import load_dotenv
from loguru import logger

from .diffing import safe_rebase
from .google_docs import GoogleDocsClient, RemoteTab
from .patcher import build_docs_requests_for_text_change
from .state import TabState, WorkspaceState, sha256_text
from .xml_codec import ir_to_docs_projection, ir_to_xml, xml_to_ir

_RUNTIME_STAGE = "startup"
_RUNTIME_CONTEXT: dict[str, str] = {}


def _sanitize_title(title: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", title.strip())
    sanitized = sanitized.strip("._")
    return sanitized or "untitled"


def _unique_file_name(existing: set[str], raw_title: str) -> str:
    base = _sanitize_title(raw_title)
    candidate = f"{base}.xml"
    index = 2
    while candidate in existing:
        candidate = f"{base}_{index}.xml"
        index += 1
    existing.add(candidate)
    return candidate


@dataclass(slots=True)
class PushConflict:
    tab_id: str
    file_name: str
    reason: str


def _vlog(verbose: bool, message: str) -> None:
    if verbose:
        click.echo(message)


def _set_stage(stage: str, **context: str) -> None:
    global _RUNTIME_STAGE, _RUNTIME_CONTEXT
    _RUNTIME_STAGE = stage
    _RUNTIME_CONTEXT = context


def _format_stage_context() -> str:
    if not _RUNTIME_CONTEXT:
        return _RUNTIME_STAGE
    context = ", ".join(f"{k}={v!r}" for k, v in sorted(_RUNTIME_CONTEXT.items()))
    return f"{_RUNTIME_STAGE} ({context})"


def _configure_logger(verbose: bool, log_file: Path, log_level: str) -> None:
    logger.remove()
    level = "DEBUG" if verbose else log_level.upper()
    logger.add(
        click.get_text_stream("stderr"),
        level=level,
        format="<level>{time:HH:mm:ss} | {level:<7} | {message}</level>",
    )
    logger.add(
        str(log_file),
        level="DEBUG",
        enqueue=False,
        backtrace=True,
        diagnose=False,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<7} | {message}",
    )


def _install_sigint_stage_logging() -> None:
    def _handler(signum: int, frame: Any) -> None:  # noqa: ARG001
        logger.warning("Interrupted by Ctrl+C while in stage: {}", _format_stage_context())
        if frame is not None:
            stack = "".join(traceback.format_stack(frame, limit=8))
            logger.debug("Active stack (most recent last):\n{}", stack.rstrip())
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _handler)


def _chunk_requests(requests: list[dict[str, Any]], chunk_size: int) -> list[list[dict[str, Any]]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    return [requests[i : i + chunk_size] for i in range(0, len(requests), chunk_size)]


def _utf16_units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _build_offset_to_doc_index_mapper(remote_tab: RemoteTab, remote_text: str) -> Callable[[int], int]:
    chunks = remote_tab.text_chunks
    if not chunks:
        return lambda offset: _utf16_units(remote_text[:offset]) + 1

    def mapper(offset: int) -> int:
        if offset <= 0:
            return chunks[0].doc_start

        for chunk in chunks:
            if chunk.plain_start <= offset < chunk.plain_end:
                prefix_len = offset - chunk.plain_start
                return chunk.doc_start + _utf16_units(chunk.text[:prefix_len])

        # Offset at or beyond last chunk: map to end of last mapped run.
        if offset >= chunks[-1].plain_end:
            return chunks[-1].doc_end

        # Fallback for sparse edge cases.
        return _utf16_units(remote_text[:offset]) + 1

    return mapper


def run_pull(document_id: str, workspace: Path, verbose: bool = False) -> int:
    client = GoogleDocsClient()
    _set_stage("pull.fetch_remote", document_id=document_id)
    _vlog(verbose, f"Fetching document {document_id} from Google Docs...")
    remote = client.get_document(document_id)

    workspace.mkdir(parents=True, exist_ok=True)
    used_names: set[str] = set()
    state = WorkspaceState(document_id=document_id, document_revision_id=remote.revision_id)
    _vlog(verbose, f"Found {len(remote.tabs)} tab(s). Writing XML files...")

    total_tabs = len(remote.tabs)
    for idx, tab in enumerate(remote.tabs, start=1):
        _set_stage("pull.write_tab", tab=tab.title, index=str(idx), total=str(total_tabs))
        file_name = _unique_file_name(used_names, tab.title)
        file_path = workspace / file_name
        xml_text = ir_to_xml(tab.ir)
        file_path.write_text(xml_text, encoding="utf-8")
        state.tabs[tab.tab_id] = TabState(
            tab_id=tab.tab_id,
            title=tab.title,
            file_name=file_name,
            content_sha256=sha256_text(xml_text),
            base_content=xml_text,
            base_remote_text=tab.plain_text,
        )
        _vlog(verbose, f"[{idx}/{total_tabs}] pulled {tab.title!r} -> {file_name}")
        if not verbose:
            print(f"pulled {tab.title!r} -> {file_name}")

    state.save(workspace)
    _set_stage("pull.done")
    print(f"wrote state: {WorkspaceState.path(workspace)}")
    return 0


def _tab_map(tabs: list[RemoteTab]) -> dict[str, RemoteTab]:
    return {tab.tab_id: tab for tab in tabs}


def _build_target_remote_text(local_xml: str) -> str:
    ir = xml_to_ir(local_xml)
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


def run_push(
    document_id: str,
    workspace: Path,
    force: bool,
    dry_run: bool,
    verbose: bool = False,
    batch_size: int = 100,
) -> int:
    started = time.monotonic()
    _set_stage("push.load_state", document_id=document_id)
    state = WorkspaceState.load(workspace)
    if state.document_id != document_id:
        raise ValueError(
            f"State file is bound to document {state.document_id!r}, not {document_id!r}"
        )
    legacy_markdown_files = [
        tab.file_name for tab in state.tabs.values() if Path(tab.file_name).suffix.lower() == ".md"
    ]
    if legacy_markdown_files:
        raise RuntimeError(
            "Legacy Markdown workspace detected in state. "
            "Run `doc pull <DOC_ID> --workspace ...` to regenerate XML files before pushing."
        )

    client = GoogleDocsClient()
    _set_stage("push.fetch_remote", document_id=document_id)
    _vlog(verbose, f"Fetching remote state for document {document_id}...")
    remote = client.get_document(document_id)
    _vlog(verbose, f"Remote revision: {remote.revision_id!r}")

    if not force and state.document_revision_id and remote.revision_id != state.document_revision_id:
        raise RuntimeError(
            "Remote revision changed since last pull. "
            "Run `doc pull` or use `doc push -f`."
        )

    remote_tabs = _tab_map(remote.tabs)
    all_requests: list[dict[str, Any]] = []
    conflicts: list[PushConflict] = []
    updated_tab_state: dict[str, TabState] = {}

    total_tabs = len(state.tabs)
    for idx, (tab_id, tab_state) in enumerate(state.tabs.items(), start=1):
        _set_stage(
            "push.process_tab",
            tab=tab_state.title,
            file=tab_state.file_name,
            index=str(idx),
            total=str(total_tabs),
        )
        _vlog(verbose, f"[{idx}/{total_tabs}] processing tab {tab_state.title!r} ({tab_state.file_name})...")
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

        local_content = file_path.read_text(encoding="utf-8")
        remote_text = remote_tab.plain_text
        local_sha = sha256_text(local_content)

        _vlog(verbose, f"[{idx}/{total_tabs}] projecting XML to Docs text...")
        _set_stage("push.project_xml", tab=tab_state.title, file=tab_state.file_name)
        target_from_local = _build_target_remote_text(local_content)
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

        _set_stage(
            "push.compute_diff",
            tab=tab_state.title,
            file=tab_state.file_name,
            remote_len=str(len(remote_text)),
            target_len=str(len(desired_remote_text)),
        )
        _vlog(verbose, f"[{idx}/{total_tabs}] computing incremental diff...")
        requests = build_docs_requests_for_text_change(
            tab_id=tab_id,
            remote_text=remote_text,
            target_text=desired_remote_text,
            offset_to_doc_index=_build_offset_to_doc_index_mapper(remote_tab, remote_text),
        )
        if requests:
            _vlog(verbose, f"[{idx}/{total_tabs}] generated {len(requests)} request(s)")
            all_requests.extend(requests)
        else:
            _vlog(verbose, f"[{idx}/{total_tabs}] no remote changes required")

        updated_tab_state[tab_id] = TabState(
            tab_id=tab_state.tab_id,
            title=remote_tab.title,
            file_name=tab_state.file_name,
            content_sha256=local_sha,
            base_content=local_content,
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
        batches = _chunk_requests(all_requests, batch_size)
        _vlog(verbose, f"Applying {len(all_requests)} request(s) in {len(batches)} batch(es)...")
        for batch_index, batch in enumerate(batches, start=1):
            _set_stage(
                "push.send_batch",
                batch=f"{batch_index}/{len(batches)}",
                requests=str(len(batch)),
            )
            _vlog(verbose, f"Sending batch {batch_index}/{len(batches)} ({len(batch)} request(s))...")
            client.batch_update(
                document_id=document_id,
                requests=batch,
                required_revision_id=required_revision_id,
            )
        print(f"applied {len(all_requests)} request(s) in {len(batches)} batch(es)")
    else:
        print("no changes to push")

    refreshed = client.get_document(document_id)
    next_state = WorkspaceState(
        document_id=document_id,
        document_revision_id=refreshed.revision_id,
        tabs=updated_tab_state if updated_tab_state else state.tabs,
    )
    next_state.save(workspace)
    _set_stage("push.done", elapsed_seconds=f"{time.monotonic() - started:.2f}")
    return 0


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--log-file", default=".docsync.log", show_default=True, type=click.Path(path_type=Path))
@click.option(
    "--log-level",
    default="INFO",
    show_default=True,
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
)
@click.pass_context
def cli(ctx: click.Context, log_file: Path, log_level: str) -> None:
    """Google Docs tabs <-> XML sync."""
    load_dotenv()
    verbose = bool(ctx.obj.get("verbose")) if isinstance(ctx.obj, dict) else False
    _configure_logger(verbose=verbose, log_file=log_file, log_level=log_level)
    _install_sigint_stage_logging()
    logger.debug("Logger initialized. log_file={!s}", log_file.resolve())


@cli.command()
@click.argument("document_id")
@click.option(
    "--workspace",
    default=".",
    show_default=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory where XML files and sync state are stored.",
)
@click.option("--verbose", is_flag=True, help="Show incremental progress logs.")
@click.pass_context
def pull(ctx: click.Context, document_id: str, workspace: Path, verbose: bool) -> None:
    """Pull tabs into local XML files."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    try:
        raise SystemExit(
            run_pull(
                document_id=document_id,
                workspace=workspace.resolve(),
                verbose=verbose,
            )
        )
    except KeyboardInterrupt as exc:
        logger.warning("Pull interrupted while in stage: {}", _format_stage_context())
        raise click.Abort() from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Pull failed in stage: {}", _format_stage_context())
        raise click.ClickException(str(exc)) from exc


@cli.command()
@click.argument("document_id")
@click.option(
    "--workspace",
    default=".",
    show_default=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory where XML files and sync state are stored.",
)
@click.option("-f", "--force", is_flag=True, help="Best-effort safe rebase mode.")
@click.option("--dry-run", is_flag=True, help="Preview push result without writing.")
@click.option("--verbose", is_flag=True, help="Show incremental progress logs.")
@click.option(
    "--batch-size",
    default=100,
    show_default=True,
    type=click.IntRange(min=1),
    help="Maximum number of Docs API requests per batchUpdate call.",
)
@click.pass_context
def push(
    ctx: click.Context,
    document_id: str,
    workspace: Path,
    force: bool,
    dry_run: bool,
    verbose: bool,
    batch_size: int,
) -> None:
    """Push local XML changes back to Google Docs."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    try:
        raise SystemExit(
            run_push(
                document_id=document_id,
                workspace=workspace.resolve(),
                force=force,
                dry_run=dry_run,
                verbose=verbose,
                batch_size=batch_size,
            )
        )
    except KeyboardInterrupt as exc:
        logger.exception("Push interrupted while in stage: {}", _format_stage_context())
        raise click.Abort() from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Push failed in stage: {}", _format_stage_context())
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":
    cli()


def main() -> None:
    """Console entrypoint used by Poetry script."""
    cli()
