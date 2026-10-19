from __future__ import annotations

from typing import TypedDict


class DocumentRecord(TypedDict, total=False):
    book_id: str
    title: str
    author: str
    source_type: str
    status: str
    progress: int
    chapter_count: int
