from __future__ import annotations

from typing import TypedDict


class ConversationRecord(TypedDict, total=False):
    id: str
    user_id: str
    title: str
    card_id: str | None
