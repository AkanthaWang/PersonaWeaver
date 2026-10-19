from typing import Any, TypedDict


class ChatResult(TypedDict):
    content: str


class StructuredExtractionResult(TypedDict):
    payload: dict[str, list[dict[str, Any]]]
