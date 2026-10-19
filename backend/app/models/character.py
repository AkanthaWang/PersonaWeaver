from __future__ import annotations

from typing import TypedDict


class CharacterRecord(TypedDict, total=False):
    id: str
    book_id: str
    name: str
    intro: str
    content: str
