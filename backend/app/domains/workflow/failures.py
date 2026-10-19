"""Extraction failure classification.

Failures are classified deterministically so the orchestrator can decide whether
a unit should be retried, re-run with a degraded prompt, or skipped without
blocking the rest of the book. No model call happens here: extraction stays
reproducible and auditable.

The kind is recorded as a short prefix inside ``extraction_units.error_message``
so no schema migration is required; callers that need the raw text can strip the
prefix with ``split``.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from backend.app.ai.extraction_pipeline import transient_error
from backend.app.ai.providers.api_types import ModelResponseError

STRUCTURE = "structure"
EMPTY = "empty"
TRANSPORT = "transport"
UNKNOWN = "unknown"
RECOVERABLE = {STRUCTURE, EMPTY, TRANSPORT}

PREFIXES = {
    STRUCTURE: "结构不符",
    EMPTY: "输出为空",
    TRANSPORT: "传输失败",
    UNKNOWN: "未归类",
}


def classify(exc: BaseException) -> str:
    """Return the failure kind for ``exc``.

    ``ValidationError`` must be checked before ``ValueError`` because it derives
    from it. ``ModelResponseError`` derives from ``RuntimeError`` but means "the
    provider returned no usable text", which is worth a different remedy than an
    arbitrary runtime error.
    """
    if isinstance(exc, ValidationError):
        return STRUCTURE
    if isinstance(exc, ModelResponseError):
        return EMPTY
    if isinstance(exc, RuntimeError) and "接口响应元数据" in str(exc):
        return EMPTY
    if isinstance(exc, json.JSONDecodeError):
        return STRUCTURE
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        return STRUCTURE
    if transient_error(exc):
        return TRANSPORT
    return UNKNOWN


def describe(exc: BaseException, limit: int = 300) -> str:
    """Return a human-readable failure description carrying the kind."""
    kind = classify(exc)
    return f"{PREFIXES[kind]}：{str(exc)[:limit]}"


def label(exc: BaseException) -> str:
    """Return the recorded message for ``exc``, prefixed with the failure kind."""
    return f"[{classify(exc)}] {describe(exc)}"


def is_recoverable(exc: BaseException) -> bool:
    """Whether the Agent may skip this unit and continue with other actions."""
    return classify(exc) in RECOVERABLE
