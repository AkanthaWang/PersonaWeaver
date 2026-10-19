from __future__ import annotations

from typing import TypedDict


class MemoryRecord(TypedDict, total=False):
    id: str
    scope: str
    content: str
