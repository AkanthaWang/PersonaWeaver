"""Run identity and lifecycle helpers. Credentials never enter graph state."""

import hashlib
import json


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def public_settings(settings):
    return {k: v for k, v in settings.items() if k not in {"api_key", "headers"}}


def identity(engine, user_id, row, settings):
    book = None
    if row.get("book_id"):
        db = engine.db.book_database(row["book_id"])
        book = {
            "revision": engine.db.one(
                "SELECT knowledge_revision FROM books WHERE book_id=?", (row["book_id"],)),
            "index": db.one("SELECT revision FROM chat_index_state WHERE id=1"),
        }
    cards = list(json.loads(row.get("character_ids") or "[]"))
    if row.get("card_id"):
        cards.append(row["card_id"])
    return digest({
        "settings": settings, "book": book,
        "conversation": {k: row.get(k) for k in (
            "book_id", "card_id", "mode", "writing_format", "character_ids",
            "knowledge_enabled", "memory_enabled",
        )},
        "cards": [engine.service.characters.owned(user_id, cid) for cid in dict.fromkeys(cards)],
    })


def erase_checkpoints(conn, cid):
    """Erase derived state in the same transaction as clearing the conversation."""
    threads = [r[0] for r in conn.execute(
        "SELECT thread_id FROM conversation_runs WHERE conversation_id=? AND thread_id IS NOT NULL", (cid,))]
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table in ("checkpoints", "writes", "checkpoint_writes", "checkpoint_blobs"):
        if table in tables:
            columns = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            if "thread_id" in columns:
                conn.executemany(f"DELETE FROM {table} WHERE thread_id=?", [(t,) for t in threads])
    conn.execute("DELETE FROM harness_events WHERE conversation_id=?", (cid,))
