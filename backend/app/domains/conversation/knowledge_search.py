"""Filtered local recall, with optional semantic recall when sending a message."""

import hashlib
import json
import re
import sqlite3

from fastapi import HTTPException

INDEX_VERSION = "cjk-bigram-v1"
SOURCE_TABLES = ("chapters", "knowledge_characters", "knowledge_facts", "knowledge_events",
                 "knowledge_relations", "knowledge_evidence", "knowledge_reviews")


def initialize_index(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chat_index_state (
            id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL DEFAULT 0,
            indexed_revision INTEGER NOT NULL DEFAULT -1, version TEXT NOT NULL DEFAULT ''
        );
        INSERT OR IGNORE INTO chat_index_state(id) VALUES(1);
        CREATE TABLE IF NOT EXISTS chat_documents (
            id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, payload TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS chat_fts USING fts5(id UNINDEXED,tokens);
    """)
    for table in SOURCE_TABLES:
        for action in ("INSERT", "UPDATE", "DELETE"):
            conn.executescript(f"""
                CREATE TRIGGER IF NOT EXISTS chat_revision_{table}_{action.lower()}
                AFTER {action} ON {table} BEGIN
                    UPDATE chat_index_state SET revision=revision+1 WHERE id=1;
                END;
            """)


def terms(text):
    output = []
    for part in re.findall(r"[\u3400-\u9fff]+|[a-zA-Z0-9_]+", text.casefold()):
        if "\u3400" <= part[0] <= "\u9fff":
            output.extend(part[i:i + 2] for i in range(len(part) - 1))
            if len(part) == 1:
                output.append(part)
        else:
            output.append(part)
    return list(dict.fromkeys(output))


def _rows(conn, table):
    return [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]


def documents(conn, book_id):
    chapters = {row["id"]: row for row in _rows(conn, "chapters") if row["book_id"] == book_id}
    evidence = {row["id"]: row for row in _rows(conn, "knowledge_evidence") if row["book_id"] == book_id}
    pending = {row["entity_id"] for row in _rows(conn, "knowledge_reviews")
               if row["book_id"] == book_id and row["state"] == "pending"}
    characters = {row["id"]: row for row in _rows(conn, "knowledge_characters")
                  if row["book_id"] == book_id and row["state"] == "active" and not row["deleted_at"] and not row["merged_into_id"]
                  and row["id"] not in pending}
    all_characters = {row["id"] for row in _rows(conn, "knowledge_characters")}

    def source(record, key, title, content, aliases=None):
        item = {"id": key, "book_id": book_id, "kind": key.split(":")[0], "title": title,
                "content": content, "aliases": aliases or [], "chapter_id": None,
                "chapter_no": None, "quote": "", "start": None, "end": None}
        ev = evidence.get(record.get("evidence_id"))
        if ev:
            chapter = chapters.get(ev["chapter_id"])
            if chapter:
                item.update(chapter_id=chapter["id"], chapter_no=chapter["chapter_no"],
                            chapter_title=chapter["title"], quote=ev["quote"])
                start, end, quote = ev["start_offset"], ev["end_offset"], ev["quote"]
                text = chapter["content"]
                if start is None and quote and text.count(quote) == 1:
                    start = text.index(quote)
                    end = start + len(quote)
                if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(text) and text[start:end] == quote:
                    item.update(start=start, end=end)
        return item

    for chapter in chapters.values():
        text = chapter["content"]
        for start in range(0, len(text), 800):
            quote = text[start:start + 1000]
            yield {"id": f"chapter:{chapter['id']}:{start}", "book_id": book_id, "kind": "chapter",
                   "title": chapter["title"], "chapter_title": chapter["title"], "aliases": [],
                   "chapter_id": chapter["id"], "chapter_no": chapter["chapter_no"],
                   "content": quote, "quote": quote, "start": start, "end": start + len(quote)}
    for row in characters.values():
        aliases = json.loads(row["aliases_json"])
        yield source(row, f"character:{row['id']}", row["canonical_name"],
                     row["canonical_name"] + "；别名：" + "、".join(aliases), aliases)
    facts = _rows(conn, "knowledge_facts")
    superseded = {r["supersedes_id"] for r in facts if r["state"] == "active" and not r["deleted_at"]}
    for table, kind in (("knowledge_facts", "fact"), ("knowledge_events", "event"), ("knowledge_relations", "relation")):
        for row in (facts if kind == "fact" else _rows(conn, table)):
            if row["book_id"] != book_id or row["state"] != "active" or row["deleted_at"] or row["id"] in pending:
                continue
            ev = evidence.get(row.get("evidence_id"))
            if ev and ev["source_type"] in {"hypothesis", "candidate", "inference"}:
                continue
            if kind == "fact":
                if row["id"] in superseded or row["source_type"] in {"hypothesis", "candidate", "inference"}:
                    continue
                entity = row["entity_id"]
                if entity in all_characters and entity not in characters:
                    continue
                name = characters.get(entity, {}).get("canonical_name", row["entity_type"])
                title = f"{name} · {row['fact_type']}"
                content = f"{title}：{row['value_json']}"
            elif kind == "event":
                title, content = row["title"], f"{row['title']}：{row['description']}"
            else:
                ids = (row["subject_id"], row["object_id"])
                if any(i in all_characters and i not in characters for i in ids):
                    continue
                names = [characters.get(i, {}).get("canonical_name", i) for i in ids]
                title = f"{names[0]} · {row['relation_type']} · {names[1]}"
                content = f"{title}：{row['value_json']}"
            yield source(row, f"{kind}:{row['id']}", title, content)


def ensure_index(db, book_id):
    with db.connect() as conn:
        state = dict(conn.execute("SELECT * FROM chat_index_state WHERE id=1").fetchone())
        counts = [conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table in ("chat_documents", "chat_fts")]
        if counts[0] != counts[1]:
            conn.execute("DELETE FROM chat_fts")
            state["version"] = ""
        if state["revision"] == state["indexed_revision"] and state["version"] == INDEX_VERSION:
            return state["revision"]
        existing = {row["id"]: row["fingerprint"] for row in conn.execute("SELECT id,fingerprint FROM chat_documents")}
        seen = set()
        for item in documents(conn, book_id):
            key = item["id"]
            seen.add(key)
            payload = json.dumps(item, ensure_ascii=False, sort_keys=True)
            fingerprint = hashlib.sha256(payload.encode()).hexdigest()
            if existing.get(key) == fingerprint and state["version"] == INDEX_VERSION:
                continue
            conn.execute("DELETE FROM chat_fts WHERE id=?", (key,))
            conn.execute("INSERT INTO chat_fts(id,tokens) VALUES(?,?)",
                         (key, " ".join(terms(item["title"] + " " + item["content"]))))
            conn.execute("INSERT INTO chat_documents VALUES(?,?,?) ON CONFLICT(id) DO UPDATE "
                         "SET fingerprint=excluded.fingerprint,payload=excluded.payload", (key, fingerprint, payload))
        for key in set(existing) - seen:
            conn.execute("DELETE FROM chat_fts WHERE id=?", (key,))
            conn.execute("DELETE FROM chat_documents WHERE id=?", (key,))
        conn.execute("UPDATE chat_index_state SET indexed_revision=?,version=? WHERE id=1",
                     (state["revision"], INDEX_VERSION))
    return state["revision"]


def retrieve(database, user_id, book_id, query, limit=12, *, use_embeddings=True):
    if not database.one("SELECT book_id FROM books WHERE book_id=? AND user_id=?", (book_id, user_id)):
        raise HTTPException(404, "关联作品不存在")
    db = database.book_database(book_id)
    try:
        revision = ensure_index(db, book_id)
    except sqlite3.DatabaseError as exc:
        if "fts" not in str(exc).lower() and "malformed" not in str(exc).lower():
            raise
        rebuild_index(db, book_id)
        revision = ensure_index(db, book_id)
    expanded = query
    for row in db.all("SELECT payload FROM chat_documents WHERE id LIKE 'character:%'"):
        character = json.loads(row["payload"])
        if any(name.casefold() in query.casefold() for name in [character["title"], *character["aliases"]] if name):
            expanded += " " + character["title"]
    tokens = terms(expanded)[:64]
    if not tokens:
        return []
    match = " OR ".join('"' + token + '"' for token in tokens)
    rows = db.all("SELECT d.payload,bm25(chat_fts) AS rank FROM chat_fts "
                  "JOIN chat_documents d ON d.id=chat_fts.id WHERE chat_fts MATCH ? ORDER BY rank LIMIT 80", (match,))
    candidates = []
    lowered = query.casefold()
    for row in rows:
        item = json.loads(row["payload"])
        exact = any(name.casefold() in lowered for name in [item["title"], *item.get("aliases", [])] if name)
        candidates.append((not exact, row["rank"], item))
    keyword = [item for _, _, item in sorted(candidates, key=lambda v: (v[0], v[1]))]
    semantic = []
    if use_embeddings and query.strip():
        from .semantic_search import recall
        indexed = [json.loads(row["payload"]) for row in db.all("SELECT payload FROM chat_documents")]
        semantic = recall(database, db, user_id, expanded, indexed, max(24, limit * 2))
    from .semantic_search import fuse
    results = fuse(keyword, semantic, limit)
    for item in results:
        item["index_revision"] = revision
        item["retrieval"] = "hybrid" if semantic else "keyword"
        # Titles and verified quotes are included in the model budget, not just the drawer.
        item["content"] = f"[{item['id']}] {item['title']}\n{item['content']}" + (
            f"\n第{item['chapter_no']}章引文：{item['quote']}" if item.get("quote") and item["kind"] != "chapter" else "")
    return results


def rebuild_index(db, book_id):
    """Rebuild derived tables only; raw chapters and knowledge are never changed."""
    with db.connect() as conn:
        conn.execute("DROP TABLE IF EXISTS chat_fts")
        conn.execute("CREATE VIRTUAL TABLE chat_fts USING fts5(id UNINDEXED,tokens)")
        conn.execute("DELETE FROM chat_documents")
        conn.execute("UPDATE chat_index_state SET indexed_revision=-1,version='' WHERE id=1")
    ensure_index(db, book_id)
