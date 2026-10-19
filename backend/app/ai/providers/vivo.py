"""vivo AIGC adapter (delegates to the shared registry)."""

from __future__ import annotations

from .registry import get_registry


def invoke(settings, messages):
    return get_registry().invoke({**settings, "api": "vivo"}, messages)


__all__ = ["invoke"]
