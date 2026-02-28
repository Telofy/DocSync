# Design Notes

## Confirmed Google Docs API capabilities

- Tab content is fetched via `documents.get(..., includeTabsContent=True)`.
- Tab-scoped writes are done by adding `tabId` to request locations/ranges.
- Incremental edits use `insertText` and `deleteContentRange`.
- Strict push uses `writeControl.requiredRevisionId` so stale writes fail.
- Suggestions are read-only from API perspective in this implementation.

## Canonical IR v1

Each tab is represented as `DocumentIR(blocks=[...])`, where each block is:

- `paragraph(text)`
- `heading(text, level=1..6)`
- `list_item(text, ordered, indent)`
- `blockquote(text)`
- `code(text)`

### Markdown to IR mapping

- `#` through `######` -> heading level.
- `-` / `*` -> unordered list item.
- `N.` -> ordered list item.
- `> ` -> blockquote.
- fenced triple-backtick block -> code.
- blank line -> empty paragraph separator.

### Docs to IR mapping

- `paragraph.paragraphStyle.namedStyleType == HEADING_N` -> heading.
- `paragraph.bullet` present -> list item.
- otherwise -> paragraph.

## Push conflict model

- `doc push` (strict):
  - requires unchanged remote revision.
  - if revision drift is detected, abort with no writes.
- `doc push -f`:
  - perform three-way safe rebase (`base`, `local`, `remote`).
  - reject overlapping change ranges.
  - write only incremental requests; no full replacement.
  - emit `.docsync_conflicts.json` and non-zero exit on unsafe rebase.
