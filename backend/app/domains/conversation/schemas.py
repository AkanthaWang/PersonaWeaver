from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ConversationCreate(BaseModel):
    title: str = Field(default="新会话", min_length=1, max_length=100)
    card_id: Optional[str] = None
    profile_id: Optional[str] = None


class ConversationUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=100)
    profile_id: Optional[str] = None
    name: Optional[str] = Field(default=None, max_length=100)


class MessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    system_prompt: str = Field(default="", max_length=12000)
    profile_id: Optional[str] = None
    parent_id: Optional[str] = None

    @field_validator("message")
    @classmethod
    def clean_message(cls, value):
        if not value.strip():
            raise ValueError("消息不能为空")
        return value.strip()


class ActiveNodeRequest(BaseModel):
    node_id: Optional[str] = None
    summary: bool = False
    summary_prompt: str = Field(default="", max_length=4000)


class CompactRequest(BaseModel):
    instructions: str = Field(default="", max_length=4000)
    profile_id: Optional[str] = None
    keep_recent_tokens: Optional[int] = Field(default=None, ge=200, le=100000)


class LabelRequest(BaseModel):
    label: Optional[str] = Field(default=None, max_length=120)


__all__ = [
    "ActiveNodeRequest",
    "CompactRequest",
    "ConversationCreate",
    "ConversationUpdate",
    "LabelRequest",
    "MessageRequest",
]
