from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class BlockKind(str, Enum):
    PARAGRAPH = "paragraph"
    HEADING = "heading"
    LIST_ITEM = "list_item"
    BLOCKQUOTE = "blockquote"
    CODE = "code"


@dataclass(slots=True)
class Block:
    kind: BlockKind
    text: str
    level: int = 0
    ordered: bool = False
    indent: int = 0


@dataclass(slots=True)
class DocumentIR:
    blocks: list[Block] = field(default_factory=list)
