from __future__ import annotations

from backend.app.ai.prompts.conversation import CARD_CONTEXT_PREFIX, CONVERSATION_GROUNDED_SYSTEM

from .compaction import to_branch_context_message, to_context_message
import json


def metadata(entry: dict) -> dict:
    value = entry.get("metadata")
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


def effective_entries(path: list[dict]) -> list[dict]:
    """Resolve checkpoints, preserving source ids for incremental compaction."""
    context = []
    for index, entry in enumerate(path):
        kind = entry.get("entry_type") or "message"
        if kind == "compaction":
            summary = entry.get("summary") or entry.get("content") or ""
            first_kept = entry.get("kept_from_node_id")
            start = next((i for i in range(index) if path[i]["id"] == first_kept), None)
            if start is not None:
                tail = [item for item in path[start:index]
                        if item.get("entry_type", "message") in {"message", "custom_message"}]
            else:
                tail = metadata(entry).get("retainedTail") or []
            context = [{**entry, **to_context_message(summary)}]
            context.extend(dict(item) for item in tail if item.get("role") in {"user", "assistant"})
        elif kind == "branch_summary":
            summary = entry.get("summary") or entry.get("content") or ""
            context.append({**entry, **to_branch_context_message(summary)})
        elif kind in {"message", "custom_message"}:
            context.append(entry)
    return context


def resolve_path(path: list[dict]) -> list[dict]:
    """Apply compaction checkpoints while walking a leaf-to-root path.

    ``path`` is ordered oldest-first. Whenever a ``compaction`` entry appears we
    replace everything before it with the summary plus the retained tail, which
    mirrors Pi's ``buildContextEntries``. ``branch_summary`` and
    ``session_info`` entries pass through as context/ignored respectively.
    """

    return [{"role": item.get("role", "assistant"), "content": item.get("content", "")}
            for item in effective_entries(path)]


def build_context(
    system_prompt: str,
    user_prompt: str,
    history: list[dict] | list[list[dict]],
    card_content: str = "",
    context_hint: str = "",
) -> list[dict[str, str]]:
    """Assemble the model message list.

    ``history`` may be a flat message list (legacy callers) or the raw path
    entries produced by the conversation repository, in which case compaction
    and branch summaries are applied. ``context_hint`` carries auxiliary
    retrieval context such as the active character card.
    """

    system = system_prompt or CONVERSATION_GROUNDED_SYSTEM
    if card_content:
        system += CARD_CONTEXT_PREFIX + card_content
    messages = _as_messages(history)
    merged = _merge_system(system, context_hint)
    return [{"role": "system", "content": merged}, *messages, {"role": "user", "content": user_prompt}]


def _as_messages(history):
    if not history:
        return []
    first = history[0]
    if isinstance(first, dict) and "entry_type" in first:
        return resolve_path(history)
    return list(history)


def _merge_system(system: str, context_hint: str) -> str:
    if not context_hint:
        return system
    return f"{system}\n\n{context_hint}"


__all__ = ["build_context", "resolve_path"]
