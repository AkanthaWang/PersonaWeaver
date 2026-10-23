from contextlib import contextmanager
from threading import Lock
from functools import wraps
import json

from fastapi import HTTPException

from backend.app.db.database import identifier, now
from backend.app.domains.characters.service import CharacterService
from backend.app.domains.settings import llm
from backend.app.domains.settings.repository import SettingsRepository

from . import budget, compaction
from .memory_context import effective_entries, metadata, resolve_path
from .mirror import sync_mirror
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


def locked(method):
    @wraps(method)
    def run(self, user_id, conversation_id, *args, **kwargs):
        with _conversation_lock(conversation_id):
            return method(self, user_id, conversation_id, *args, **kwargs)
    return run


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
            "character_ids": json.loads(item.get("character_ids") or "[]"),
            "messages": [_public_entry(entry) for entry in path if entry.get("entry_type") in {"message", "custom_message"}],
            "context": _public_path(path),
            "tree": _public_tree(self.repo.tree(conversation_id)),
            "tokens": compaction.messages_tokens(resolve_path(path)),
        }

    def create(self, user_id: str, payload):
        book_id = payload.book_id
        if payload.card_id:
            card = self.characters.owned(user_id, payload.card_id)
            if book_id and book_id != card["book_id"]:
                raise HTTPException(422, "角色卡与关联作品不一致")
            book_id = card["book_id"]
        if book_id:
            self.characters.book_owned(user_id, book_id)
        self._validate_cast(user_id, book_id, payload.character_ids)
        profile_id = self._validated_profile(user_id, payload.profile_id)
        conversation_id, stamp = identifier("conversation"), now()
        self.repo.create(
            (conversation_id, user_id, payload.title, payload.card_id, profile_id, None, None, self.store.cwd, stamp, stamp)
        )
        self.db.execute(
            "UPDATE conversations SET book_id=?,mode=?,knowledge_enabled=?,memory_enabled=?,writing_format=?,character_ids=? WHERE id=?",
            (book_id, payload.mode or ("roleplay" if payload.card_id else "assistant"),
             int(payload.knowledge_enabled), int(payload.memory_enabled), payload.writing_format,
             json.dumps(payload.character_ids), conversation_id),
        )
        row = self.get_owned(user_id, conversation_id)
        self._ensure_session_file(row)
        sync_mirror(self.db, conversation_id)
        return self.get(user_id, conversation_id)

    @locked
    def rename(self, user_id: str, conversation_id: str, payload):
        row = self.get_owned(user_id, conversation_id)
        stamp = now()
        fields = payload.model_dump(exclude_unset=True)
        self._validate_cast(user_id, fields.get("book_id", row.get("book_id")),
                            fields.get("character_ids", json.loads(row.get("character_ids") or "[]")) or [])
        if "book_id" in fields:
            if row["card_id"]:
                card = self.characters.owned(user_id, row["card_id"])
                if fields["book_id"] != card["book_id"]:
                    raise HTTPException(422, "角色会话不能关联其他作品")
            if fields["book_id"]:
                self.characters.book_owned(user_id, fields["book_id"])
        for field in ("book_id", "mode", "knowledge_enabled", "memory_enabled", "writing_format", "character_ids"):
            if field in fields:
                if field != "book_id" and fields[field] is None:
                    raise HTTPException(422, "设置不能为空")
                value = json.dumps(fields[field]) if field == "character_ids" else fields[field]
                self.db.execute(f"UPDATE conversations SET {field}=?,updated_at=? WHERE id=?",
                                (value, stamp, conversation_id))
        if payload.title is not None:
            self.repo.rename(conversation_id, payload.title, stamp)
        if payload.profile_id is not None:
            profile_id = self._validated_profile(user_id, payload.profile_id)
            self.repo.set_profile(conversation_id, profile_id, stamp)
        if getattr(payload, "name", None) is not None:
            self._append_session_info(row, payload.name, stamp)
        return self.get(user_id, conversation_id)

    def delete(self, user_id: str, conversation_id: str):
        row = self.get_owned(user_id, conversation_id)
        with _conversation_lock(conversation_id):
            self.repo.delete(conversation_id)
            sync_mirror(self.db, conversation_id)
        return {"ok": True}

    def clear(self, user_id: str, conversation_id: str):
        self.get_owned(user_id, conversation_id)
        with _conversation_lock(conversation_id):
            self.repo.clear_messages(conversation_id, now())
            sync_mirror(self.db, conversation_id)
        return {"ok": True}

    @locked
    def fork(self, user_id: str, conversation_id: str):
        """Copy the active branch into a brand new conversation (Pi ``/clone``)."""

        row = self.get_owned(user_id, conversation_id)
        entries = self.repo.path(conversation_id, row.get("active_leaf_id"))
        if not any(entry.get("entry_type") == "message" for entry in entries):
            raise HTTPException(400, "当前会话没有可复制的消息")
        new_id, stamp = identifier("conversation"), now()
        title = (row["title"] or "会话") + " 副本"
        ids = {entry["id"]: identifier("node") for entry in entries}
        versions = self.db.all("SELECT * FROM conversation_memory_versions WHERE conversation_id=? ORDER BY seq", (conversation_id,))
        versions = [v for v in versions if v["anchor_id"] in ids]
        version_ids = {v["id"]: identifier("memory_version") for v in versions}
        memory_ids = {v["memory_id"]: identifier("memory") for v in versions}
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO conversations(id,user_id,title,card_id,profile_id,active_leaf_id,session_cwd,"
                "created_at,updated_at,book_id,mode,knowledge_enabled,memory_enabled) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (new_id, user_id, title, row["card_id"], row["profile_id"], ids.get(row["active_leaf_id"]),
                 self.store.cwd, stamp, stamp, row["book_id"], row["mode"], row["knowledge_enabled"], row["memory_enabled"]),
            )
            conn.execute("UPDATE conversations SET writing_format=?,character_ids=? WHERE id=?",
                         (row["writing_format"], row["character_ids"], new_id))
            for entry in entries:
                meta = metadata(entry).copy()
                for tail in meta.get("retainedTail") or []:
                    if tail.get("id"):
                        tail["id"] = ids.get(tail["id"])
                if meta.get("fromId"):
                    meta["fromId"] = ids.get(meta["fromId"])
                meta.pop("request_id", None)
                conn.execute(
                    "INSERT INTO messages(node_id,conversation_id,parent_id,entry_type,role,content,created_at,"
                    "summary,tokens_before,kept_from_node_id,label,metadata) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (ids[entry["id"]], new_id, ids.get(entry["parent_id"]), entry["entry_type"], entry["role"],
                     entry["content"], entry["created_at"], entry["summary"], entry["tokens_before"],
                     ids.get(entry["kept_from_node_id"]), entry["label"], json.dumps(meta, ensure_ascii=False)),
                )
            for v in versions:
                conn.execute(
                    "INSERT INTO conversation_memory_versions(id,conversation_id,memory_id,anchor_id,category,memory_key,"
                    "content,deleted,locked,source_ids,origin,supersedes_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (version_ids[v["id"]], new_id, memory_ids[v["memory_id"]], ids[v["anchor_id"]], v["category"],
                     v["memory_key"], v["content"], v["deleted"], v["locked"],
                     json.dumps([ids[i] for i in json.loads(v["source_ids"]) if i in ids]), v["origin"],
                     version_ids.get(v["supersedes_id"]), v["created_at"]),
                )
        new_row = self.get_owned(user_id, new_id)
        self._ensure_session_file(new_row)
        sync_mirror(self.db, new_id)
        return self.get(user_id, new_id)

    def _validate_cast(self, user_id, book_id, card_ids):
        for card_id in card_ids:
            if self.characters.owned(user_id, card_id)["book_id"] != book_id:
                raise HTTPException(422, "出场角色必须属于关联作品")

    # ------------------------------------------------------------------ tree
    @locked
    def set_active_node(self, user_id: str, conversation_id: str, payload):
        row = self.get_owned(user_id, conversation_id)
        if payload.node_id and not self.repo.node(conversation_id, payload.node_id):
            raise HTTPException(404, "消息节点不存在")
        stamp = now()
        previous_leaf = row.get("active_leaf_id")
        summary = None
        if payload.summary and previous_leaf and previous_leaf != payload.node_id:
            summary = self._summarize_abandoned_branch(row, previous_leaf, payload.node_id, payload.summary_prompt, stamp)
        self.repo.set_active_leaf(conversation_id, summary["id"] if summary else payload.node_id, stamp)
        sync_mirror(self.db, conversation_id)
        result = self.get(user_id, conversation_id)
        if summary:
            result["branch_summary"] = summary
        return result

    @locked
    def set_label(self, user_id: str, conversation_id: str, node_id: str, label):
        self.get_owned(user_id, conversation_id)
        node = self.repo.node(conversation_id, node_id)
        if not node:
            raise HTTPException(404, "消息节点不存在")
        cleaned = (label or "").strip() or None
        self.repo.set_label(conversation_id, node_id, cleaned)
        sync_mirror(self.db, conversation_id)
        return {"ok": True, "node_id": node_id, "label": cleaned}

    # ------------------------------------------------------------------ sending
    def send(self, user_id: str, conversation_id: str, payload, user_prompt: str = ""):
        """Synchronous compatibility callers use the same graph as HTTP clients."""
        import asyncio
        from .generation import GenerationEngine

        async def generate():
            engine = GenerationEngine(self.db)
            try:
                live = await engine.start(user_id, conversation_id, payload, user_prompt)
                if live.task:
                    await live.task
                result = engine.result(user_id, conversation_id, live.request_id)
                if result["status"] == "completed" and result.get("memory_enabled"):
                    try:
                        await engine.memory.settle(user_id, conversation_id,
                                                   self.repo.path(conversation_id, result["active_leaf_id"]))
                    except Exception as exc:
                        result["memory_warning"] = llm.error_message(exc)
                return result
            finally:
                await engine.shutdown()
        return asyncio.run(generate())

    # ------------------------------------------------------------------ compaction
    def compact(self, user_id: str, conversation_id: str, payload):
        row = self.get_owned(user_id, conversation_id)
        with _conversation_lock(conversation_id):
            row = self.get_owned(user_id, conversation_id)
            entries = self.repo.path(conversation_id, row.get("active_leaf_id"))
            messages = [entry for entry in effective_entries(entries)
                        if entry.get("entry_type") != "compaction"]
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
            retained_tail = compaction.to_retained_tail(kept)
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
        sync_mirror(self.db, row["id"])

    def _summarize_abandoned_branch(self, row, previous_leaf, target_id, instructions, stamp):
        entries = self.repo.path(row["id"], previous_leaf)
        ancestor = _common_ancestor(entries, self.repo.path(row["id"], target_id))
        start = 0
        if ancestor is not None:
            start = next(i for i, entry in enumerate(entries) if entry["id"] == ancestor) + 1
        abandoned = resolve_path(entries[start:])
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
        return {"id": node_id, "summary": summary}

    def _mirror_exchange(self, row, parent_id, user_node_id, assistant_node_id, message, reply, stamp, settings):
        return sync_mirror(self.db, row["id"])

    def _mirror_compaction(self, row, node_id, parent, summary, tokens_before, kept_from, retained_tail, stamp, settings):
        return sync_mirror(self.db, row["id"])


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
        "metadata": metadata(entry),
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
