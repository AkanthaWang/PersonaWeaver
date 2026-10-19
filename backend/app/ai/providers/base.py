"""Provider contracts shared by the registry and its adapters."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ChatProvider(Protocol):
    """Minimal chat completion interface."""

    def invoke(self, messages: list[dict[str, str]]) -> str: ...


class ChatSettings(dict):
    """Marker type documenting the flat settings dict passed to providers.

    Recognised keys: ``api`` / ``api_protocol`` / ``provider``, ``base_url``,
    ``model``, ``api_key``, ``headers``, ``temperature``, ``top_p``,
    ``max_tokens``, ``timeout_seconds`` and ``request_id``.
    """

    @classmethod
    def of(cls, **values: Any) -> "ChatSettings":
        return cls(values)


__all__ = ["ChatProvider", "ChatSettings"]
