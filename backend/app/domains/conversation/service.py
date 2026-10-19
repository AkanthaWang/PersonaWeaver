from contextlib import contextmanager
from threading import Lock

from fastapi import HTTPException

from backend.app.ai.prompts.conversation import CONVERSATION_GROUNDED_SYSTEM
from backend.app.db.database import identifier, now
from backend.app.domains.characters.service import CharacterService
from backend.app.domains.settings import llm
from backend.app.domains.settings.repository import SettingsRepository

from . import compaction
from .memory_context import build_context
from .repository import ConversationRepository
from .session_store import SessionStore

_busy: set[str] = set()
_busy_lock = Lock()


@contextmanager
def _conversation_lock(conversation_id: str):
    with _busy_lock:
        if conversation_id in _busy:
            raise HTTPException(409, "该会话正在生成回复")
        _busy.add(conversation_id)
    try:
        yield
    finally:
        with _busy_lock:
            _busy.discard(conversation_id)


class ConversationService:
    def __init__(self, db):
        self.db = db
        self.repo = ConversationRepository(db)
        self.characters = CharacterService(db)
        self.settings = SettingsRepository(db)
        self.store = SessionStore(db.path.parent)

    def _validated_profile(self, user_id: str, profile_id):
        """Return a usable profile id, raising when the caller passed a bad one."""

        if not profile_id:
            return None
        profile = self.settings.profile_for_user(user_id, profile_id)
        if not profile:
            raise HTTPException(404, "模型配置不存在")
        if profile.get("model_type", "llm") != "llm":
            raise HTTPException(422, "请选择大语言模型用于对话")
        return profile["id"]

    # ------------------------------------------------------------------ sessions
    def _ensure_session_file(self, row):
        """Create the JSONL session file lazily and cache its path on the row."""

        conversation_id = row["id"]
        path = row.get("session_file")
        if path:
            return self._session_path(path)
        target = self.store.path_for(conversation_id, row["created_at"])
        self.store.ensure_header(target, conversation_id, row["created_at"])
        self.repo.set_session_file(conversation_id, str(target), now())
        row["session_file"] = str(target)
        return target

    def _session_path(self, value):
        from pathlib import Path

        return Path(value)

    def list(self, user_id: str):
        return {"conversations": self.repo.list_for_user(user_id)}

    def get_owned(self, user_id: str, conversation_id: str):
        item = self.repo.get_owned(user_id, conversation_id)
        if not item:
            raise HTTPException(404, "会话不存在")
        return item

    def get(self, user_id: str, conversation_id: str):
        item = self.get_owned(user_id, conversation_id)
        active_leaf_id = item.get("active_leaf_id")
        path = self.repo.path(conversation_id, active_leaf_id)
        return {
            **item,
            "messages": [entry for entry in path if entry.get("entry_type") in {"message", "custom_message"}],
            "context": _public_path(path),
            "tree": _public_tree(self.repo.tree(conversation_id)),
            "tokens": compaction.messages_tokens([{"content": entry.get("content")} for entry in path]),
        }

    def create(self, user_id: str, payload):
        if payload.card_id:
            self.characters.owned(user_id, payload.card_id)
        profile_id = self._validated_profile(user_id, payload.profile_id)
        conversation_id, stamp = identifier("conversation"), now()
        self.repo.create(
            (conversation_id, user_id, payload.title, payload.card_id, profile_id, None, None, self.store.cwd, stamp, stamp)
        )
        row = self.get_owned(user_id, conversation_id)
        self._ensure_session_file(row)
        return self.get_owned(user_id, conversation_id)

    def rename(self, user_id: str, conversation_id: str, payload):
        row = self.get_owned(user_id, conversation_id)
        stamp = now()
        if payload.title is not None:
            self.repo.rename(conversation_id, payload.title, stamp)
        if payload.profile_id is not None:
            profile_id = self._validated_profile(user_id, payload.profile_id)
            self.repo.set_profile(conversation_id, profile_id, stamp)
        if getattr(payload, "name", None) is not None:
            self._append_session_info(row, payload.name, stamp)
        return self.get_owned(user_id, conversation_id)

    def delete(self, user_id: str, conversation_id: str):
        row = self.get_owned(user_id, conversation_id)
        with _conversation_lock(conversation_id):
            self.repo.delete(conversation_id)
            if row.get("session_file"):
                self._session_path(row["session_file"]).unlink(missing_ok=True)
        return {"ok": True}

    def clear(self, user_id: str, conversation_id: str):
        self.get_owned(user_id, conversation_id)
        with _conversation_lock(conversation_id):
            self.repo.clear_messages(conversation_id, now())
        return {"ok": True}

    def fork(self, user_id: str, conversation_id: str):
        """Copy the active branch into a brand new conversation (Pi ``/clone``)."""

        row = self.get_owned(user_id, conversation_id)
        entries = self.repo.path(conversation_id, row.get("active_leaf_id"))
        messages = [entry for entry in entries if entry.get("entry_type") == "message"]
        if not messages:
            raise HTTPException(400, "当前会话没有可复制的消息")
        new_id, stamp = identifier("conversation"), now()
        title = (row["title"] or "会话") + " 副本"
        self.repo.create((new_id, user_id, title, row["card_id"], row["profile_id"], None, None, self.store.cwd, stamp, stamp))
        new_row = self.get_owned(user_id, new_id)
        path = self._ensure_session_file(new_row)
        parent = None
        for entry in messages:
            node_id = identifier("message")
            self.repo.append_entry(
                {
                    "id": node_id,
                    "conversation_id": new_id,
                    "parent_id": parent,
                    "entry_type": "message",
                    "role": entry["role"],
                    "content": entry["content"],
                    "created_at": entry.get("created_at") or stamp,
                }
            )
            self.store.append(path, _jsonl_message(node_id, parent, entry, new_id, new_row["created_at"]))
            parent = node_id
        if parent:
            self.repo.set_active_leaf(new_id, parent, now())
        return self.get_owned(user_id, new_id)

    # ------------------------------------------------------------------ tree
    def set_active_node(self, user_id: str, conversation_id: str, payload):
        row = self.get_owned(user_id, conversation_id)
        if payload.node_id and not self.repo.node(conversation_id, payload.node_id):
            raise HTTPException(404, "消息节点不存在")
        stamp = now()
        previous_leaf = row.get("active_leaf_id")
        summary = None
        if payload.summary and previous_leaf and previous_leaf != payload.node_id:
            summary = self._summarize_abandoned_branch(row, previous_leaf, payload.node_id, payload.summary_prompt, stamp)
        self.repo.set_active_leaf(conversation_id, payload.node_id, stamp)
        result = self.get(user_id, conversation_id)
        if summary:
            result["branch_summary"] = summary
        return result

    def set_label(self, user_id: str, conversation_id: str, node_id: str, label):
        self.get_owned(user_id, conversation_id)
        node = self.repo.node(conversation_id, node_id)
        if not node:
            raise HTTPException(404, "消息节点不存在")
        cleaned = (label or "").strip() or None
        self.repo.set_label(conversation_id, node_id, cleaned)
        return {"ok": True, "node_id": node_id, "label": cleaned}

    # ------------------------------------------------------------------ sending
    def send(self, user_id: str, conversation_id: str, payload, user_prompt: str = ""):
        row = self.get_owned(user_id, conversation_id)
        parent_id = payload.parent_id if payload.parent_id is not None else row.get("active_leaf_id")
        if parent_id and not self.repo.node(conversation_id, parent_id):
            raise HTTPException(404, "父消息节点不存在")
        with _conversation_lock(conversation_id):
            path = self.repo.path(conversation_id, parent_id)
            system = payload.system_prompt or user_prompt or CONVERSATION_GROUNDED_SYSTEM
            card_content = ""
            if row["card_id"]:
                card_content = self.characters.owned(user_id, row["card_id"])["content"]
            messages = build_context(system, payload.message, path, card_content)
            profile_id = payload.profile_id or row.get("profile_id")
            settings = llm.load_settings_for_profile(self.db, user_id, profile_id)
            try:
                reply = llm.chat(settings, messages)
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(502, llm.error_message(exc)) from exc
            title = payload.message[:30] if row["title"] == "新会话" else row["title"]
            stamp = now()
            user_node_id = identifier("message")
            assistant_node_id = identifier("message")
            self.repo.append_exchange(
                conversation_id, parent_id, user_node_id, assistant_node_id, payload.message, reply, title, stamp,
                metadata={"provider": settings.get("provider"), "model": settings.get("model"),
                          "usage": {"output": compaction.estimate_tokens(reply)}},
            )
            self._mirror_exchange(row, parent_id, user_node_id, assistant_node_id, payload.message, reply, stamp, settings)
        return {
            "response": reply,
            "active_leaf_id": assistant_node_id,
            "messages": self.get(user_id, conversation_id)["messages"],
            "tree": self.get(user_id, conversation_id)["tree"],
        }

    # ------------------------------------------------------------------ compaction
    def compact(self, user_id: str, conversation_id: str, payload):
        row = self.get_owned(user_id, conversation_id)
        with _conversation_lock(conversation_id):
            entries = self.repo.path(conversation_id, row.get("active_leaf_id"))
            messages = [entry for entry in entries if entry.get("entry_type") == "message"]
            if len(messages) < 3:
                raise HTTPException(400, "对话内容过少，无需压缩")
            tokens_before = compaction.messages_tokens(messages)
            cut = compaction.choose_cut_point(messages, payload.keep_recent_tokens or compaction.DEFAULT_KEEP_RECENT_TOKENS)
            if cut <= 0:
                raise HTTPException(400, "当前上下文仍在预算内，无需压缩")
            to_summarize = messages[:cut]
            kept = messages[cut:]
            previous = _latest_summary(entries)
            profile_id = payload.profile_id or row.get("profile_id")
            settings = llm.load_settings_for_profile(self.db, user_id, profile_id)
            prompt = compaction.build_prompt(
                [{"role": item["role"], "content": item["content"]} for item in to_summarize],
                previous_summary=previous,
                instructions=payload.instructions or "",
            )
            try:
                summary = compaction.normalize_summary(llm.chat(settings, prompt))
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(502, llm.error_message(exc)) from exc
            stamp = now()
            node_id = identifier("compaction")
            parent = row.get("active_leaf_id")
            kept_from = kept[0]["id"] if kept else None
            retained_tail = compaction.to_retained_tail([{"role": item["role"], "content": item["content"]} for item in kept])
            self.repo.append_compaction(
                conversation_id, node_id, parent, summary, tokens_before, kept_from, retained_tail, stamp,
            )
            self._mirror_compaction(row, node_id, parent, summary, tokens_before, kept_from, retained_tail, stamp, settings)
        return {**self.get(user_id, conversation_id), "compaction": {"id": node_id, "tokens_before": tokens_before, "summary": summary}}

    # ------------------------------------------------------------------ internals
    def _append_session_info(self, row, name: str, stamp: str):
        node_id = identifier("session")
        self.repo.append_entry(
            {
                "id": node_id,
                "conversation_id": row["id"],
                "parent_id": row.get("active_leaf_id"),
                "entry_type": "session_info",
                "role": "sessionInfo",
                "content": name,
                "created_at": stamp,
                "metadata": {"name": name},
            }
        )
        path = self._ensure_session_file(row)
        self.store.append(path, {"type": "session_info", "id": node_id, "parentId": row.get("active_leaf_id"),
                                 "timestamp": stamp, "name": name})

    def _summarize_abandoned_branch(self, row, previous_leaf, target_id, enabled, instructions, stamp):
        entries = self.repo.path(row["id"], previous_leaf)
        ancestor = _common_ancestor(entries, self.repo.path(row["id"], target_id))
        abandoned = [entry for entry in entries if entry.get("entry_type") == "message"]
        if ancestor is not None:
            index = next((i for i, entry in enumerate(abandoned) if entry["id"] == ancestor), None)
            if index is not None:
                abandoned = abandoned[index + 1:]
        if not abandoned:
            return None
        profile_id = row.get("profile_id")
        settings = llm.load_settings_for_profile(self.db, row["user_id"], profile_id)
        prompt = compaction.build_branch_prompt(
            [{"role": item["role"], "content": item["content"]} for item in abandoned],
            instructions=instructions or "",
        )
        try:
            summary = compaction.normalize_summary(llm.chat(settings, prompt))
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(502, llm.error_message(exc)) from exc
        node_id = identifier("branch")
        self.repo.append_branch_summary(row["id"], node_id, target_id, summary, previous_leaf, stamp)
        path = self._ensure_session_file(row)
        self.store.append(path, {"type": "branch_summary", "id": node_id, "parentId": target_id,
                                 "timestamp": stamp, "summary": summary, "fromId": previous_leaf})
        return {"id": node_id, "summary": summary}

    def _mirror_exchange(self, row, parent_id, user_node_id, assistant_node_id, message, reply, stamp, settings):
        path = self._ensure_session_file(row)
        session_id = row["id"]
        self.store.append(path, _jsonl_message(user_node_id, parent_id, {"role": "user", "content": message}, session_id, stamp))
        self.store.append(path, {
            "type": "message", "id": assistant_node_id, "parentId": user_node_id, "timestamp": stamp,
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": reply}],
                "provider": settings.get("provider"),
                "model": settings.get("model"),
                "stopReason": "stop",
            },
        })

    def _mirror_compaction(self, row, node_id, parent, summary, tokens_before, kept_from, retained_tail, stamp, settings):
        path = self._ensure_session_file(row)
        entry = {
            "type": "compaction", "id": node_id, "parentId": parent, "timestamp": stamp,
            "summary": summary, "tokensBefore": tokens_before,
        }
        if kept_from:
            entry["firstKeptEntryId"] = kept_from
        if retained_tail:
            entry["retainedTail"] = retained_tail
        entry["model"] = settings.get("model")
        self.store.append(path, entry)


def _public_path(path: list[dict]) -> list[dict]:
    return [_public_entry(entry) for entry in path]


def _public_tree(tree: list[dict]) -> list[dict]:
    return [_public_entry(entry) for entry in tree]


def _public_entry(entry: dict) -> dict:
    item = {
        "id": entry["id"],
        "parent_id": entry.get("parent_id"),
        "entry_type": entry.get("entry_type") or "message",
        "role": entry.get("role"),
        "content": entry.get("content"),
        "created_at": entry.get("created_at"),
        "label": entry.get("label"),
    }
    if entry.get("summary"):
        item["summary"] = entry["summary"]
    if entry.get("tokens_before") is not None:
        item["tokens_before"] = entry["tokens_before"]
    if entry.get("kept_from_node_id"):
        item["kept_from_node_id"] = entry["kept_from_node_id"]
    return item


def _jsonl_message(node_id, parent_id, source, session_id, stamp=None):
    role = source.get("role") or "assistant"
    return {
        "type": "message",
        "id": node_id,
        "parentId": parent_id,
        "timestamp": source.get("created_at") or stamp or session_id,
        "message": {"role": role, "content": source.get("content", "")},
    }


def _latest_summary(entries: list[dict]) -> str:
    for entry in reversed(entries):
        if entry.get("entry_type") == "compaction" and entry.get("summary"):
            return entry["summary"]
    return ""


def _leaf_of(entries: list[dict]):
    return entries[-1]["id"] if entries else None


def _common_ancestor(current: list[dict], target: list[dict]):
    current_ids = {entry["id"] for entry in current}
    for entry in reversed(target):
        if entry["id"] in current_ids:
            return entry["id"]
    return None
