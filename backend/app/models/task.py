from __future__ import annotations

from typing import TypedDict


class TaskRecord(TypedDict, total=False):
    id: str
    book_id: str
    task_type: str
    status: str
    progress: int
    current_step: str
