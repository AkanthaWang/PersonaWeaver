"""Context compaction and branch summarization.

Mirrors Pi's ``compaction`` / ``branch-summarization`` behaviour without the
TUI: older messages are summarised into a structured checkpoint so the model
context stays bounded, and abandoned tree branches can be summarised when the
active leaf moves.

The summary format follows Pi's ``docs/compaction.md``.
"""

from __future__ import annotations

import re
import math

from backend.app.ai.prompts.conversation import (
    BRANCH_CONTEXT_PREFIX,
    COMPACTION_BRANCH_HISTORY_PREFIX,
    COMPACTION_BRANCH_PROMPT,
    COMPACTION_CONTEXT_PREFIX,
    COMPACTION_EXTRA_PREFIX,
    COMPACTION_HISTORY_PREFIX,
    COMPACTION_PREVIOUS_SUMMARY_PREFIX,
    COMPACTION_SUMMARY_PROMPT,
)

# Kept as aliases for callers that imported the historical names.
SUMMARY_PROMPT = COMPACTION_SUMMARY_PROMPT
BRANCH_PROMPT = COMPACTION_BRANCH_PROMPT

# Rough character budgets. Chinese text is roughly one token per character,
# latin text closer to one token per four characters; a blended constant keeps
# the estimate honest without a tokenizer dependency.
CHARS_PER_TOKEN = 2.4
# Keep roughly this many tokens of recent history unsummarised.
DEFAULT_KEEP_RECENT_TOKENS = 2000
# Summary prompt output budget.
SUMMARY_MAX_CHARS = 4000


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    # Unknown tokenizers: non-ASCII text must not be estimated as English.
    ascii_count = sum(ord(char) < 128 for char in text)
    return max(1, math.ceil(ascii_count / 3) + (len(text) - ascii_count) * 2)


def messages_tokens(messages: list[dict]) -> int:
    return 3 + sum(4 + estimate_tokens(item.get("content") or "") for item in messages)


def extract_files(messages: list[dict]) -> dict:
    """Collect referenced workspace files mentioned in the conversation."""

    read_files, modified_files = [], []
    pattern = re.compile(r"(?:读取|查看|read|opened?)\s*[:：]?\s*([\w./\\-]+\.[A-Za-z0-9]+)")
    modify = re.compile(r"(?:写入|修改|保存|write|edit(?:ed)?)\s*[:：]?\s*([\w./\\-]+\.[A-Za-z0-9]+)")
    for item in messages:
        content = item.get("content") or ""
        read_files.extend(pattern.findall(content))
        modified_files.extend(modify.findall(content))
    return {"readFiles": _dedupe(read_files), "modifiedFiles": _dedupe(modified_files)}


def choose_cut_point(messages: list[dict], keep_recent_tokens: int = DEFAULT_KEEP_RECENT_TOKENS) -> int:
    """Return the index where summarised history ends and kept history begins.

    Walks backwards accumulating tokens until the recent budget is reached.
    Never cuts inside an assistant/tool exchange: the cut must land on a user
    message (or index 0 when the whole history fits the budget).
    """

    total = messages_tokens(messages)
    if total <= keep_recent_tokens or len(messages) <= 2:
        return 0
    accumulated = 0
    cut = len(messages)
    for index in range(len(messages) - 1, -1, -1):
        accumulated += estimate_tokens(messages[index].get("content") or "")
        cut = index
        if accumulated >= keep_recent_tokens:
            break
    while cut > 0 and messages[cut].get("role") != "user":
        cut -= 1
    return cut


def serialize_messages(messages: list[dict]) -> str:
    """Render history as labelled text so the model summarises rather than replies."""

    labels = {"user": "[User]", "assistant": "[Assistant]", "system": "[System]"}
    lines = []
    for item in messages:
        content = (item.get("content") or "").strip()
        if not content:
            continue
        lines.append(f"{labels.get(item.get('role'), '[Other]')}: {content}")
    return "\n\n".join(lines)


def build_prompt(messages: list[dict], previous_summary: str = "", instructions: str = "") -> list[dict]:
    parts = [COMPACTION_SUMMARY_PROMPT]
    if instructions:
        parts.append(COMPACTION_EXTRA_PREFIX + instructions)
    if previous_summary:
        parts.append(COMPACTION_PREVIOUS_SUMMARY_PREFIX + previous_summary)
    parts.append(COMPACTION_HISTORY_PREFIX + serialize_messages(messages))
    return [{"role": "user", "content": "\n\n".join(parts)}]


def build_branch_prompt(messages: list[dict], instructions: str = "") -> list[dict]:
    parts = [COMPACTION_BRANCH_PROMPT]
    if instructions:
        parts.append(COMPACTION_EXTRA_PREFIX + instructions)
    parts.append(COMPACTION_BRANCH_HISTORY_PREFIX + serialize_messages(messages))
    return [{"role": "user", "content": "\n\n".join(parts)}]


def normalize_summary(text: str) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) > SUMMARY_MAX_CHARS:
        cleaned = cleaned[:SUMMARY_MAX_CHARS].rstrip() + "\n…"
    return cleaned


def to_context_message(summary: str) -> dict:
    """Wrap a compaction summary as a model-visible message."""

    return {
        "role": "assistant",
        "content": COMPACTION_CONTEXT_PREFIX + summary,
    }


def to_branch_context_message(summary: str) -> dict:
    return {
        "role": "assistant",
        "content": BRANCH_CONTEXT_PREFIX + summary,
    }


def to_retained_tail(messages: list[dict]) -> list[dict]:
    """JSON-serialisable retained tail stored on the compaction entry."""

    tail = []
    for item in messages:
        tail.append({key: item[key] for key in ("id", "role", "content") if key in item})
    return tail


def _dedupe(values: list[str]) -> list[str]:
    seen, ordered = set(), []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


__all__ = [
    "BRANCH_PROMPT",
    "CHARS_PER_TOKEN",
    "DEFAULT_KEEP_RECENT_TOKENS",
    "SUMMARY_PROMPT",
    "build_branch_prompt",
    "build_prompt",
    "choose_cut_point",
    "estimate_tokens",
    "extract_files",
    "messages_tokens",
    "normalize_summary",
    "serialize_messages",
    "to_branch_context_message",
    "to_context_message",
    "to_retained_tail",
]
