from __future__ import annotations

from typing import TypedDict


class UserRecord(TypedDict, total=False):
    user_id: str
    username: str
    email: str
    avatar: str | None
    prompt: str
