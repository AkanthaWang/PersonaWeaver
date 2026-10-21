"""Recoverable JSONL projection. SQLite commits always win over mirror errors."""

import logging
from pathlib import Path

from backend.app.db.database import now
from .memory_context import metadata
from .repository import ConversationRepository
from .session_store import SessionStore

logger = logging.getLogger(__name__)


def sync_mirror(db, conversation_id):
    repo = ConversationRepository(db)
    pending = db.one("SELECT * FROM conversation_mirrors WHERE conversation_id=?", (conversation_id,))
    try:
        row = db.one("SELECT * FROM conversations WHERE id=?", (conversation_id,))
        if not row:
            if pending and pending["path"]:
                Path(pending["path"]).unlink(missing_ok=True)
        else:
            store = SessionStore(db.path.parent)
            path = Path(row["session_file"]) if row["session_file"] else store.path_for(row["id"], row["created_at"])
            if not row["session_file"]:
                repo.set_session_file(row["id"], str(path), row["updated_at"])
            entries = []
            for node in repo.tree(conversation_id):
                kind = node["entry_type"]
                entry = {"type": kind, "id": node["id"], "parentId": node["parent_id"],
                         "timestamp": node["created_at"]}
                info = metadata(node)
                if kind in {"message", "custom_message"}:
                    entry["message"] = {"role": node["role"], "content": node["content"], **info}
                elif kind == "compaction":
                    entry.update(summary=node["summary"], tokensBefore=node["tokens_before"],
                                 firstKeptEntryId=node["kept_from_node_id"], **info)
                else:
                    entry.update(content=node["content"], summary=node.get("summary"), **info)
                if node.get("label"):
                    entry["label"] = node["label"]
                entries.append(entry)
            store.rebuild(path, row["id"], row["created_at"], entries)
        db.execute("DELETE FROM conversation_mirrors WHERE conversation_id=?", (conversation_id,))
        return None
    except (OSError, ValueError) as exc:
        # Never expose file paths, exception contents or credentials to the browser.
        logger.warning("Session mirror pending: %s (%s)", conversation_id, type(exc).__name__)
        db.execute(
            "INSERT INTO conversation_mirrors(conversation_id,path,error,updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(conversation_id) DO UPDATE SET error=excluded.error,updated_at=excluded.updated_at",
            (conversation_id, pending["path"] if pending else None, type(exc).__name__, now()),
        )
        return "会话已保存，JSONL 镜像待同步"


def recover_mirrors(db):
    for row in db.all("SELECT conversation_id FROM conversation_mirrors"):
        sync_mirror(db, row["conversation_id"])
