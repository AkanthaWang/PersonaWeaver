from __future__ import annotations

from backend.app.ai.prompts.conversation import CARD_CONTEXT_PREFIX, CONVERSATION_GROUNDED_SYSTEM

from .compaction import to_branch_context_message, to_context_message


def resolve_path(path: list[dict]) -> list[dict]:
    """Apply compaction checkpoints while walking a leaf-to-root path.

    ``path`` is ordered oldest-first. Whenever a ``compaction`` entry appears we
    replace everything before it with the summary plus the retained tail, which
    mirrors Pi's ``buildContextEntries``. ``branch_summary`` and
    ``session_info`` entries pass through as context/ignored respectively.
    """

    context: list[dict] = []
    for entry in path:
        entry_type = entry.get("entry_type") or "message"
        if entry_type == "compaction":
            summary = entry.get("summary") or entry.get("content") or ""
            # The compaction entry sits after the history it replaces; drop that
            # history and inject the structured summary in its place. Entries
            # appended after the compaction (the kept tail) flow through below.
            context = [to_context_message(summary)]
        elif entry_type == "branch_summary":
            summary = entry.get("summary") or entry.get("content") or ""
            context.append(to_branch_context_message(summary))
        elif entry_type == "session_info":
            continue
        else:
            context.append({"role": entry.get("role", "assistant"), "content": entry.get("content", "")})
    return context


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
