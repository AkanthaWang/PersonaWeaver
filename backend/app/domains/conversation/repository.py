from __future__ import annotations

import json

from backend.app.db.base_repository import SQLiteRepository

# Columns selected for every tree entry; kept in sync with ``node``/``tree``.
ENTRY_COLUMNS = (
    "node_id AS id, conversation_id, parent_id, entry_type, role, content, created_at, "
    "summary, tokens_before, kept_from_node_id, label, metadata"
)


class ConversationRepository(SQLiteRepository):
    def list_for_user(self, user_id: str):
        return self.all(
            "SELECT id,user_id,title,card_id,profile_id,active_leaf_id,session_file,created_at,updated_at "
            "FROM conversations WHERE user_id=? ORDER BY updated_at DESC",
            (user_id,),
        )

    def get_owned(self, user_id: str, conversation_id: str):
        return self.one("SELECT * FROM conversations WHERE id=? AND user_id=?", (conversation_id, user_id))

    def create(self, values):
        return self.execute(
            "INSERT INTO conversations "
            "(id,user_id,title,card_id,profile_id,active_leaf_id,session_file,session_cwd,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            values,
        )

    def rename(self, conversation_id: str, title: str, stamp: str):
        return self.execute("UPDATE conversations SET title=?,updated_at=? WHERE id=?", (title, stamp, conversation_id))

    def set_profile(self, conversation_id: str, profile_id, stamp: str):
        return self.execute(
            "UPDATE conversations SET profile_id=?,updated_at=? WHERE id=?", (profile_id, stamp, conversation_id),
        )

    def set_active_leaf(self, conversation_id: str, node_id: str | None, stamp: str):
        return self.execute(
            "UPDATE conversations SET active_leaf_id=?,updated_at=? WHERE id=?", (node_id, stamp, conversation_id),
        )

    def set_session_file(self, conversation_id: str, session_file: str, stamp: str):
        return self.execute(
            "UPDATE conversations SET session_file=?,updated_at=? WHERE id=?", (session_file, stamp, conversation_id),
        )

    def delete(self, conversation_id: str):
        from backend.app.ai.harness.storage import erase_checkpoints
        with self.database.connect() as conn:
            erase_checkpoints(conn, conversation_id)
            return conn.execute("DELETE FROM conversations WHERE id=?", (conversation_id,)).rowcount

    def node(self, conversation_id: str, node_id: str):
        return self.one(
            f"SELECT {ENTRY_COLUMNS} FROM messages WHERE conversation_id=? AND node_id=?",
            (conversation_id, node_id),
        )

    def tree(self, conversation_id: str):
        return self.all(
            f"SELECT {ENTRY_COLUMNS} FROM messages WHERE conversation_id=? ORDER BY messages.id",
            (conversation_id,),
        )

    def children(self, conversation_id: str, node_id: str | None):
        if node_id is None:
            return self.all(
                f"SELECT {ENTRY_COLUMNS} FROM messages "
                "WHERE conversation_id=? AND parent_id IS NULL ORDER BY messages.id",
                (conversation_id,),
            )
        return self.all(
            f"SELECT {ENTRY_COLUMNS} FROM messages WHERE conversation_id=? AND parent_id=? ORDER BY messages.id",
            (conversation_id, node_id),
        )

    def path(self, conversation_id: str, active_leaf_id: str | None):
        """All entries from the leaf back to the root, oldest first."""

        if not active_leaf_id:
            return []
        return self.all(
            "WITH RECURSIVE path(seq,node_id,parent_id,entry_type,role,content,created_at,summary,tokens_before,"
            "kept_from_node_id,label,metadata,conversation_id) AS ("
            "  SELECT id,node_id,parent_id,entry_type,role,content,created_at,summary,tokens_before,"
            "kept_from_node_id,label,metadata,conversation_id FROM messages "
            "  WHERE conversation_id=? AND node_id=?"
            "  UNION ALL "
            "  SELECT m.id,m.node_id,m.parent_id,m.entry_type,m.role,m.content,m.created_at,m.summary,m.tokens_before,"
            "m.kept_from_node_id,m.label,m.metadata,m.conversation_id FROM messages m "
            "  JOIN path p ON p.parent_id=m.node_id WHERE m.conversation_id=?"
            ") "
            "SELECT node_id AS id,conversation_id,parent_id,entry_type,role,content,created_at,summary,tokens_before,"
            "kept_from_node_id,label,metadata FROM path ORDER BY seq",
            (conversation_id, active_leaf_id, conversation_id),
        )

    def history(self, conversation_id: str, active_leaf_id: str | None, limit: int = 40):
        entries = self.path(conversation_id, active_leaf_id)
        messages = [entry for entry in entries if entry["entry_type"] in {"message", "custom_message"}]
        return [{"role": entry["role"], "content": entry["content"]} for entry in messages[-limit:]]

    def append_entry(self, entry: dict):
        return self.execute(
            "INSERT INTO messages(node_id,conversation_id,parent_id,entry_type,role,content,created_at,"
            "summary,tokens_before,kept_from_node_id,label,metadata) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                entry["id"], entry["conversation_id"], entry.get("parent_id"), entry.get("entry_type", "message"),
                entry.get("role", "assistant"), entry.get("content", ""), entry["created_at"],
                entry.get("summary"), entry.get("tokens_before"), entry.get("kept_from_node_id"),
                entry.get("label"), _dump(entry.get("metadata")),
            ),
        )

    def append_exchange(
        self,
        conversation_id: str,
        parent_id: str | None,
        user_node_id: str,
        assistant_node_id: str,
        user_message: str,
        reply: str,
        title: str,
        stamp: str,
        metadata: dict | None = None,
        run_update: dict | None = None,
    ):
        with self.database.connect() as conn:
            conn.execute(
                "INSERT INTO messages(node_id,conversation_id,parent_id,entry_type,role,content,created_at,metadata) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (user_node_id, conversation_id, parent_id, "message", "user", user_message, stamp, None),
            )
            conn.execute(
                "INSERT INTO messages(node_id,conversation_id,parent_id,entry_type,role,content,created_at,metadata) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (
                    assistant_node_id, conversation_id, user_node_id, "message", "assistant", reply, stamp,
                    _dump(metadata),
                ),
            )
            conn.execute(
                "UPDATE conversations SET title=?,active_leaf_id=?,updated_at=? WHERE id=?",
                (title, assistant_node_id, stamp, conversation_id),
            )
            if run_update:
                conn.execute(
                    "UPDATE conversation_runs SET status=?,reply=?,user_node_id=?,assistant_node_id=?,"
                    "error=?,usage=?,updated_at=? WHERE conversation_id=? AND request_id=?",
                    (run_update["status"], reply, user_node_id, assistant_node_id, run_update.get("error"),
                     _dump(run_update.get("usage", {})), stamp, conversation_id, run_update["request_id"]),
                )
                if run_update["status"] == "completed" and run_update.get("memory_enabled"):
                    conn.execute(
                        "INSERT OR IGNORE INTO conversation_memory_jobs"
                        "(id,conversation_id,request_id,status,created_at,updated_at) VALUES(?,?,?,'queued',?,?)",
                        (assistant_node_id, conversation_id, run_update["request_id"], stamp, stamp),
                    )

    def append_compaction(
        self,
        conversation_id: str,
        node_id: str,
        parent_id: str | None,
        summary: str,
        tokens_before: int,
        kept_from_node_id: str | None,
        retained_tail: list | None,
        stamp: str,
    ):
        with self.database.connect() as conn:
            conn.execute(
                "INSERT INTO messages(node_id,conversation_id,parent_id,entry_type,role,content,created_at,"
                "summary,tokens_before,kept_from_node_id,metadata) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    node_id, conversation_id, parent_id, "compaction", "compaction",
                    summary or "", stamp, summary, tokens_before, kept_from_node_id,
                    _dump({"retainedTail": retained_tail} if retained_tail else None),
                ),
            )
            conn.execute(
                "UPDATE conversations SET active_leaf_id=?,updated_at=? WHERE id=?",
                (node_id, stamp, conversation_id),
            )

    def append_branch_summary(
        self,
        conversation_id: str,
        node_id: str,
        parent_id: str | None,
        summary: str,
        from_id: str | None,
        stamp: str,
    ):
        return self.execute(
            "INSERT INTO messages(node_id,conversation_id,parent_id,entry_type,role,content,created_at,"
            "summary,metadata) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                node_id, conversation_id, parent_id, "branch_summary", "branchSummary",
                summary or "", stamp, summary, _dump({"fromId": from_id}),
            ),
        )

    def set_label(self, conversation_id: str, node_id: str, label: str | None):
        return self.execute(
            "UPDATE messages SET label=? WHERE conversation_id=? AND node_id=?",
            (label, conversation_id, node_id),
        )

    def clear_messages(self, conversation_id: str, stamp: str):
        with self.database.connect() as conn:
            from backend.app.ai.harness.storage import erase_checkpoints
            erase_checkpoints(conn, conversation_id)
            conn.execute("DELETE FROM conversation_memory_jobs WHERE conversation_id=?", (conversation_id,))
            conn.execute("DELETE FROM conversation_memory_versions WHERE conversation_id=?", (conversation_id,))
            # Retain idempotency tombstones, but erase cleared conversation text.
            conn.execute(
                "UPDATE conversation_runs SET cleared=1,status='interrupted',parent_id=NULL,message='',reply='',"
                "user_node_id=NULL,assistant_node_id=NULL,sources='[]',context_usage='{}',usage='{}',result_json=NULL,"
                "validation='{}',request_json='{}',state_fingerprint='',checkpoint_id=NULL,thread_id=NULL,"
                "error='历史已清空，旧请求不会重新生成',updated_at=? WHERE conversation_id=?", (stamp, conversation_id),
            )
            conn.execute("DELETE FROM messages WHERE conversation_id=?", (conversation_id,))
            conn.execute("UPDATE conversations SET active_leaf_id=NULL,updated_at=? WHERE id=?", (stamp, conversation_id))


def _dump(value):
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)
