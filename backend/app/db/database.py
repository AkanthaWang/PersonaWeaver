from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import threading
import uuid


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


# Book databases whose character frequencies were already restored in this process.
_FREQUENCY_BACKFILLED: set[str] = set()


def identifier(prefix):
    return f"{prefix}_{uuid.uuid4().hex}"


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY, username TEXT NOT NULL COLLATE NOCASE UNIQUE,
    password_hash TEXT NOT NULL, email TEXT NOT NULL DEFAULT '',
    avatar TEXT, prompt TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_settings (
    user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    provider TEXT NOT NULL DEFAULT 'ollama', base_url TEXT NOT NULL DEFAULT 'http://127.0.0.1:11434',
    model TEXT NOT NULL DEFAULT 'qwen2.5:7b', api_key TEXT NOT NULL DEFAULT '',
    temperature REAL NOT NULL DEFAULT 0.7, top_p REAL NOT NULL DEFAULT 0.9,
    max_tokens INTEGER NOT NULL DEFAULT 2048, timeout_seconds INTEGER NOT NULL DEFAULT 60
);
CREATE TABLE IF NOT EXISTS model_profiles (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    name TEXT NOT NULL, provider TEXT NOT NULL, provider_name TEXT NOT NULL DEFAULT '',
    model_type TEXT NOT NULL DEFAULT 'llm',
    test_status TEXT NOT NULL DEFAULT 'untested', test_message TEXT NOT NULL DEFAULT '', tested_at TEXT,
    api_protocol TEXT NOT NULL DEFAULT '', headers_json TEXT NOT NULL DEFAULT '{}', base_url TEXT NOT NULL,
    model TEXT NOT NULL, api_key TEXT NOT NULL DEFAULT '',
    temperature REAL NOT NULL DEFAULT 0.7, top_p REAL NOT NULL DEFAULT 0.9,
    max_tokens INTEGER NOT NULL DEFAULT 2048, timeout_seconds INTEGER NOT NULL DEFAULT 60,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE(user_id, name)
);
CREATE TABLE IF NOT EXISTS model_profile_state (
    user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    active_profile_id TEXT NOT NULL REFERENCES model_profiles(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS model_selections (
    user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    extraction_model_id TEXT, embedding_model_id TEXT, reranker_model_id TEXT,
    reranker_top_k INTEGER NOT NULL DEFAULT 5 CHECK(reranker_top_k BETWEEN 1 AND 100)
);
CREATE TABLE IF NOT EXISTS books (
    book_id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    title TEXT NOT NULL, author TEXT NOT NULL DEFAULT '', language TEXT NOT NULL DEFAULT 'zh-CN',
    source_type TEXT NOT NULL, file_name TEXT NOT NULL, source_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ready', progress INTEGER NOT NULL DEFAULT 0,
    err_message TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chapters (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
    chapter_no INTEGER NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL, word_count INTEGER NOT NULL,
    source_start INTEGER, source_end INTEGER,
    split_method TEXT NOT NULL DEFAULT 'unknown',
    confidence REAL NOT NULL DEFAULT 0,
    text_path TEXT,
    UNIQUE(book_id, chapter_no)
);
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
    task_type TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', progress INTEGER NOT NULL DEFAULT 0,
    current_step TEXT NOT NULL DEFAULT '', error_message TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chapter_vectors (
    chapter_id TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    model_key TEXT NOT NULL, content_hash TEXT NOT NULL, vector_json TEXT NOT NULL,
    PRIMARY KEY(chapter_id, model_key)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_task_per_book
    ON tasks(book_id) WHERE status IN ('pending', 'running');
CREATE TABLE IF NOT EXISTS task_logs (
    id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    level TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS extractions (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
    chapter_id TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    content TEXT NOT NULL, model_name TEXT NOT NULL, created_at TEXT NOT NULL,
    UNIQUE(book_id, chapter_id)
);
CREATE TABLE IF NOT EXISTS summaries (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
    type TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE(book_id, type)
);
CREATE TABLE IF NOT EXISTS cards (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
    name TEXT NOT NULL, intro TEXT NOT NULL DEFAULT '', content TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(book_id, name)
);
CREATE TABLE IF NOT EXISTS extraction_units (
    id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
    chapter_id TEXT REFERENCES chapters(id) ON DELETE CASCADE,
    kind TEXT NOT NULL, unit_key TEXT NOT NULL, fingerprint TEXT NOT NULL,
    status TEXT NOT NULL, payload TEXT, error_message TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE(task_id,kind,unit_key)
);
CREATE INDEX IF NOT EXISTS extraction_unit_cache
    ON extraction_units(book_id,kind,unit_key,fingerprint,status);
CREATE TABLE IF NOT EXISTS knowledge_entities (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
    kind TEXT NOT NULL, name TEXT NOT NULL, source_ids TEXT NOT NULL, content TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS knowledge_entities_by_book ON knowledge_entities(book_id,kind);
CREATE TABLE IF NOT EXISTS knowledge_evidence (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL, chapter_id TEXT, chunk_id TEXT,
    quote TEXT NOT NULL, source_type TEXT NOT NULL DEFAULT 'explicit_fact',
    start_offset INTEGER, end_offset INTEGER, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_characters (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL, canonical_name TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]', frequency INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'active',
    merged_into_id TEXT, deleted_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE(book_id, canonical_name)
);
CREATE TABLE IF NOT EXISTS knowledge_facts (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL, entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL, fact_type TEXT NOT NULL, value_json TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'active', version INTEGER NOT NULL DEFAULT 1,
    supersedes_id TEXT, evidence_id TEXT, source_type TEXT NOT NULL DEFAULT 'agent',
    locked_by_user INTEGER NOT NULL DEFAULT 0, deleted_at TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS knowledge_facts_current
    ON knowledge_facts(book_id, entity_type, entity_id, state, deleted_at);
CREATE TABLE IF NOT EXISTS knowledge_events (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL, title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '', story_time_start TEXT, story_time_end TEXT,
    chapter_no INTEGER, sequence_no INTEGER, state TEXT NOT NULL DEFAULT 'active',
    evidence_id TEXT, deleted_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_clues (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL, title TEXT NOT NULL,
    original_text TEXT NOT NULL, possible_meaning TEXT NOT NULL DEFAULT '',
    first_chapter_no INTEGER, state TEXT NOT NULL DEFAULT 'candidate',
    confidence REAL NOT NULL DEFAULT 0, evidence_id TEXT, deleted_at TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_relations (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL, subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL, relation_type TEXT NOT NULL, object_type TEXT NOT NULL,
    object_id TEXT NOT NULL, value_json TEXT NOT NULL DEFAULT '{}',
    state TEXT NOT NULL DEFAULT 'active', evidence_id TEXT, deleted_at TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_changes (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL, entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL, operation TEXT NOT NULL, before_json TEXT,
    after_json TEXT, reason TEXT NOT NULL DEFAULT '', operator_type TEXT NOT NULL,
    operator_id TEXT, batch_id TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_merges (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL, entity_type TEXT NOT NULL,
    source_id TEXT NOT NULL, target_id TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
    operator_type TEXT NOT NULL, created_at TEXT NOT NULL, undone_at TEXT
);
CREATE TABLE IF NOT EXISTS knowledge_reviews (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL, review_type TEXT NOT NULL,
    entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, payload_json TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending', resolution_json TEXT,
    created_at TEXT NOT NULL, resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS knowledge_reviews_pending ON knowledge_reviews(book_id,state,created_at);
CREATE TABLE IF NOT EXISTS entity_resolutions (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
    action TEXT NOT NULL, source_ids TEXT NOT NULL, other_source_ids TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS storylines (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL,
    content TEXT NOT NULL, input_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ready', error_message TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE(book_id)
);
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    title TEXT NOT NULL, card_id TEXT REFERENCES cards(id) ON DELETE SET NULL,
    profile_id TEXT REFERENCES model_profiles(id) ON DELETE SET NULL,
    active_leaf_id TEXT,
    session_file TEXT, session_cwd TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL UNIQUE,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    parent_id TEXT REFERENCES messages(node_id) ON DELETE CASCADE,
    entry_type TEXT NOT NULL DEFAULT 'message',
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'compaction', 'branchSummary', 'label', 'sessionInfo')),
    content TEXT NOT NULL, created_at TEXT NOT NULL,
    summary TEXT, tokens_before INTEGER, kept_from_node_id TEXT, label TEXT, metadata TEXT
);
CREATE INDEX IF NOT EXISTS books_by_user ON books(user_id, created_at);
CREATE INDEX IF NOT EXISTS conversations_by_user ON conversations(user_id, updated_at);
PRAGMA user_version = 1;
"""

BOOK_SCHEMA = """
CREATE TABLE IF NOT EXISTS chapters (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL,
    chapter_no INTEGER NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL, word_count INTEGER NOT NULL,
    source_start INTEGER, source_end INTEGER,
    split_method TEXT NOT NULL DEFAULT 'unknown',
    confidence REAL NOT NULL DEFAULT 0,
    text_path TEXT,
    UNIQUE(book_id, chapter_no)
);
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL,
    task_type TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', progress INTEGER NOT NULL DEFAULT 0,
    current_step TEXT NOT NULL DEFAULT '', error_message TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    request_json TEXT NOT NULL DEFAULT '{}', model_profile_id TEXT,
    config_fingerprint TEXT, input_fingerprint TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0, parent_task_id TEXT,
    reused_units INTEGER NOT NULL DEFAULT 0, stage TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_task_per_book
    ON tasks(book_id) WHERE status IN ('pending', 'running');
CREATE TABLE IF NOT EXISTS chapter_vectors (
    chapter_id TEXT NOT NULL, model_key TEXT NOT NULL, content_hash TEXT NOT NULL, vector_json TEXT NOT NULL,
    PRIMARY KEY(chapter_id, model_key)
);
CREATE TABLE IF NOT EXISTS task_logs (
    id TEXT PRIMARY KEY, task_id TEXT NOT NULL,
    level TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS extractions (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL, chapter_id TEXT NOT NULL,
    content TEXT NOT NULL, model_name TEXT NOT NULL, created_at TEXT NOT NULL,
    UNIQUE(book_id, chapter_id)
);
CREATE TABLE IF NOT EXISTS summaries (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL,
    type TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE(book_id, type)
);
CREATE TABLE IF NOT EXISTS extraction_units (
    id TEXT PRIMARY KEY, task_id TEXT NOT NULL, book_id TEXT NOT NULL,
    chapter_id TEXT, kind TEXT NOT NULL, unit_key TEXT NOT NULL, fingerprint TEXT NOT NULL,
    status TEXT NOT NULL, payload TEXT, error_message TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE(task_id, kind, unit_key)
);
CREATE INDEX IF NOT EXISTS extraction_unit_cache
    ON extraction_units(book_id, kind, unit_key, fingerprint, status);
CREATE TABLE IF NOT EXISTS knowledge_entities (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL,
    kind TEXT NOT NULL, name TEXT NOT NULL, source_ids TEXT NOT NULL, content TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS knowledge_entities_by_book ON knowledge_entities(book_id, kind);
CREATE TABLE IF NOT EXISTS knowledge_evidence (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL, chapter_id TEXT, chunk_id TEXT,
    quote TEXT NOT NULL, source_type TEXT NOT NULL DEFAULT 'explicit_fact',
    start_offset INTEGER, end_offset INTEGER, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_characters (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL, canonical_name TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]', frequency INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'active',
    merged_into_id TEXT, deleted_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE(book_id, canonical_name)
);
CREATE TABLE IF NOT EXISTS knowledge_facts (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL, entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL, fact_type TEXT NOT NULL, value_json TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'active', version INTEGER NOT NULL DEFAULT 1,
    supersedes_id TEXT, evidence_id TEXT, source_type TEXT NOT NULL DEFAULT 'agent',
    locked_by_user INTEGER NOT NULL DEFAULT 0, deleted_at TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS knowledge_facts_current
    ON knowledge_facts(book_id, entity_type, entity_id, state, deleted_at);
CREATE TABLE IF NOT EXISTS knowledge_events (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL, title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '', story_time_start TEXT, story_time_end TEXT,
    chapter_no INTEGER, sequence_no INTEGER, state TEXT NOT NULL DEFAULT 'active',
    evidence_id TEXT, deleted_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_clues (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL, title TEXT NOT NULL,
    original_text TEXT NOT NULL, possible_meaning TEXT NOT NULL DEFAULT '',
    first_chapter_no INTEGER, state TEXT NOT NULL DEFAULT 'candidate',
    confidence REAL NOT NULL DEFAULT 0, evidence_id TEXT, deleted_at TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_relations (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL, subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL, relation_type TEXT NOT NULL, object_type TEXT NOT NULL,
    object_id TEXT NOT NULL, value_json TEXT NOT NULL DEFAULT '{}',
    state TEXT NOT NULL DEFAULT 'active', evidence_id TEXT, deleted_at TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_changes (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL, entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL, operation TEXT NOT NULL, before_json TEXT,
    after_json TEXT, reason TEXT NOT NULL DEFAULT '', operator_type TEXT NOT NULL,
    operator_id TEXT, batch_id TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_merges (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL, entity_type TEXT NOT NULL,
    source_id TEXT NOT NULL, target_id TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
    operator_type TEXT NOT NULL, created_at TEXT NOT NULL, undone_at TEXT
);
CREATE TABLE IF NOT EXISTS knowledge_reviews (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL, review_type TEXT NOT NULL,
    entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, payload_json TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending', resolution_json TEXT,
    created_at TEXT NOT NULL, resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS knowledge_reviews_pending ON knowledge_reviews(book_id,state,created_at);
CREATE TABLE IF NOT EXISTS entity_resolutions (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL,
    action TEXT NOT NULL, source_ids TEXT NOT NULL, other_source_ids TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS storylines (
    id TEXT PRIMARY KEY, book_id TEXT NOT NULL,
    content TEXT NOT NULL, input_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ready', error_message TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE(book_id)
);
PRAGMA user_version = 1;
"""

BOOK_SCOPED_TABLES = {
    "chapters", "tasks", "chapter_vectors", "task_logs", "extractions", "summaries",
    "extraction_units", "knowledge_entities", "entity_resolutions",
    "knowledge_evidence", "knowledge_characters", "knowledge_facts",
    "knowledge_events", "knowledge_clues", "knowledge_relations",
    "knowledge_changes", "knowledge_merges", "storylines",
    "knowledge_reviews",
}


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._book_database_cache = {}
        self._book_database_lock = threading.RLock()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, 1}:
                raise RuntimeError(f"Unsupported database schema version: {version}; refusing to overwrite.")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA)
            book_columns = {row[1] for row in conn.execute("PRAGMA table_info(books)")}
            if "knowledge_revision" not in book_columns:
                conn.execute("ALTER TABLE books ADD COLUMN knowledge_revision INTEGER NOT NULL DEFAULT 0")
            task_columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
            for column, definition in (
                ("request_json", "TEXT NOT NULL DEFAULT '{}'"),
                ("model_profile_id", "TEXT"),
                ("config_fingerprint", "TEXT"),
                ("input_fingerprint", "TEXT"),
                ("cancel_requested", "INTEGER NOT NULL DEFAULT 0"),
                ("parent_task_id", "TEXT"),
                ("reused_units", "INTEGER NOT NULL DEFAULT 0"),
                ("stage", "TEXT NOT NULL DEFAULT ''"),
            ):
                if column not in task_columns:
                    conn.execute(f"ALTER TABLE tasks ADD COLUMN {column} {definition}")
            chapter_columns = {row[1] for row in conn.execute("PRAGMA table_info(chapters)").fetchall()}
            for column, definition in (
                ("source_start", "INTEGER"),
                ("source_end", "INTEGER"),
                ("split_method", "TEXT NOT NULL DEFAULT 'unknown'"),
                ("confidence", "REAL NOT NULL DEFAULT 0"),
                ("text_path", "TEXT"),
            ):
                if column not in chapter_columns:
                    conn.execute(f"ALTER TABLE chapters ADD COLUMN {column} {definition}")
            for database in (conn,):
                character_columns = {row[1] for row in database.execute("PRAGMA table_info(knowledge_characters)").fetchall()}
                if "frequency" not in character_columns:
                    database.execute(
                        "ALTER TABLE knowledge_characters ADD COLUMN frequency INTEGER NOT NULL DEFAULT 0"
                    )
            profile_columns = {row[1] for row in conn.execute("PRAGMA table_info(model_profiles)").fetchall()}
            for column, definition in (
                ("provider_name", "TEXT NOT NULL DEFAULT ''"),
                ("api_protocol", "TEXT NOT NULL DEFAULT ''"),
                ("headers_json", "TEXT NOT NULL DEFAULT '{}'"),
                ("model_type", "TEXT NOT NULL DEFAULT 'llm'"),
                ("test_status", "TEXT NOT NULL DEFAULT 'untested'"),
                ("test_message", "TEXT NOT NULL DEFAULT ''"),
                ("tested_at", "TEXT"),
            ):
                if column not in profile_columns:
                    conn.execute(f"ALTER TABLE model_profiles ADD COLUMN {column} {definition}")
            # Conversations may pin a model profile; older rows fall back to the
            # active profile at send time. Conversation messages are now a tree;
            # legacy linear rows are migrated into one path.
            conversation_columns = {row[1] for row in conn.execute("PRAGMA table_info(conversations)").fetchall()}
            if "profile_id" not in conversation_columns:
                conn.execute(
                    "ALTER TABLE conversations ADD COLUMN profile_id TEXT REFERENCES model_profiles(id) ON DELETE SET NULL"
                )
            if "active_leaf_id" not in conversation_columns:
                conn.execute("ALTER TABLE conversations ADD COLUMN active_leaf_id TEXT")
            for column, definition in (
                ("session_file", "TEXT"),
                ("session_cwd", "TEXT NOT NULL DEFAULT ''"),
            ):
                if column not in conversation_columns:
                    conn.execute(f"ALTER TABLE conversations ADD COLUMN {column} {definition}")
            message_columns = {row[1] for row in conn.execute("PRAGMA table_info(messages)").fetchall()}
            if "node_id" not in message_columns:
                conn.execute("ALTER TABLE messages ADD COLUMN node_id TEXT")
            # Populate tree identifiers before rebuilding a legacy table: the
            # rebuilt schema makes ``node_id`` required.
            message_rows = conn.execute(
                "SELECT id, conversation_id FROM messages WHERE node_id IS NULL ORDER BY conversation_id, id"
            ).fetchall()
            parent_by_conversation = {}
            parent_links = []
            for message in message_rows:
                node_id = f"message_{message['id']}"
                parent_id = parent_by_conversation.get(message["conversation_id"])
                conn.execute("UPDATE messages SET node_id=? WHERE id=?", (node_id, message["id"]))
                parent_links.append((parent_id, message["id"]))
                parent_by_conversation[message["conversation_id"]] = node_id
            self._widen_message_roles(conn)
            # ``_widen_message_roles`` may rebuild a legacy table with all
            # current columns, so refresh the column set before adding fields.
            message_columns = {row[1] for row in conn.execute("PRAGMA table_info(messages)").fetchall()}
            if "parent_id" not in message_columns:
                conn.execute("ALTER TABLE messages ADD COLUMN parent_id TEXT REFERENCES messages(node_id) ON DELETE CASCADE")
                message_columns.add("parent_id")
            for parent_id, message_id in parent_links:
                conn.execute("UPDATE messages SET parent_id=? WHERE id=?", (parent_id, message_id))
            for column, definition in (
                ("entry_type", "TEXT NOT NULL DEFAULT 'message'"),
                ("summary", "TEXT"),
                ("tokens_before", "INTEGER"),
                ("kept_from_node_id", "TEXT"),
                ("label", "TEXT"),
                ("metadata", "TEXT"),
            ):
                if column not in message_columns:
                    conn.execute(f"ALTER TABLE messages ADD COLUMN {column} {definition}")
            conn.execute("UPDATE messages SET entry_type='message' WHERE entry_type IS NULL")
            leaf_rows = conn.execute(
                "SELECT conversation_id, node_id FROM messages WHERE node_id IS NOT NULL ORDER BY conversation_id, id"
            ).fetchall()
            active_leaf_by_conversation = {}
            for message in leaf_rows:
                active_leaf_by_conversation[message["conversation_id"]] = message["node_id"]
            for conversation_id, active_leaf_id in active_leaf_by_conversation.items():
                conn.execute(
                    "UPDATE conversations SET active_leaf_id=COALESCE(active_leaf_id, ?) WHERE id=?",
                    (active_leaf_id, conversation_id),
                )
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS messages_node_id_unique ON messages(node_id)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS messages_by_conversation_entry "
                "ON messages(conversation_id, entry_type, id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS messages_by_conversation_parent ON messages(conversation_id, parent_id, id)"
            )
            # Existing installations only have one active model row. Preserve it as
            # a named profile so users can start switching without losing settings.
            rows = conn.execute(
                "SELECT * FROM model_settings WHERE user_id NOT IN "
                "(SELECT user_id FROM model_profile_state)"
            ).fetchall()
            for row in rows:
                profile_id = identifier("model")
                timestamp = now()
                conn.execute(
                    "INSERT OR IGNORE INTO model_profiles "
                    "(id,user_id,name,provider,base_url,model,api_key,temperature,top_p,max_tokens,timeout_seconds,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (profile_id, row["user_id"], "当前配置", row["provider"], row["base_url"], row["model"],
                     row["api_key"], row["temperature"], row["top_p"], row["max_tokens"], row["timeout_seconds"],
                     timestamp, timestamp),
                )
                profile = conn.execute(
                    "SELECT id FROM model_profiles WHERE user_id=? AND name=?",
                    (row["user_id"], "当前配置"),
                ).fetchone()
                if profile:
                    conn.execute(
                        "INSERT OR IGNORE INTO model_profile_state(user_id,active_profile_id) VALUES (?,?)",
                        (row["user_id"], profile["id"]),
                    )
            from backend.app.domains.conversation.migrations import initialize_conversations
            initialize_conversations(conn)
            # Background workers cannot survive a process restart.
            active = conn.execute("SELECT id, book_id FROM tasks WHERE status IN ('pending','running')").fetchall()
            for task in active:
                conn.execute(
                    "UPDATE extraction_units SET status='failed',error_message=?,updated_at=? "
                    "WHERE task_id=? AND status='running'",
                    ("服务重启，当前请求已中断", now(), task["id"]),
                )
                conn.execute(
                    "UPDATE tasks SET status='failed', error_message=?, current_step=?, updated_at=? WHERE id=?",
                    ("服务重启，任务已中断，请重新执行", "已中断", now(), task["id"]),
                )
                conn.execute(
                    "UPDATE books SET status='failed', err_message=?, updated_at=? WHERE book_id=?",
                    ("服务重启，任务已中断，请重新执行", now(), task["book_id"]),
                )
        self.migrate_book_databases()
        self.recover_book_tasks()

    def book_database(self, book_id: str):
        safe_id = "".join(char for char in book_id if char.isalnum() or char in "-_")
        if not safe_id:
            raise ValueError("Invalid book id")
        with self._book_database_lock:
            database = self._book_database_cache.get(safe_id)
            if database is None:
                database = BookDatabase(
                    self.path.parent / "novel" / safe_id / "extraction.sqlite3",
                    self,
                )
                database.initialize()
                self._book_database_cache[safe_id] = database
            return database

    def migrate_book_databases(self):
        """Move existing book-scoped rows out of the shared database."""

        books = self.all("SELECT book_id FROM books")
        for book in books:
            book_id = book["book_id"]
            scoped = self.book_database(book_id)
            with self.connect() as source, scoped.connect() as target:
                source_tables = {
                    row[0] for row in source.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                for table in BOOK_SCOPED_TABLES & source_tables:
                    columns = [row[1] for row in source.execute(f"PRAGMA table_info({table})")]
                    if "book_id" not in columns:
                        continue
                    rows = source.execute(
                        f"SELECT {','.join(columns)} FROM {table} WHERE book_id=?",
                        (book_id,),
                    ).fetchall()
                    if rows:
                        placeholders = ",".join("?" for _ in columns)
                        target.executemany(
                            f"INSERT OR IGNORE INTO {table}({','.join(columns)}) VALUES({placeholders})",
                            [tuple(row) for row in rows],
                        )
                task_ids = [row[0] for row in source.execute(
                    "SELECT id FROM tasks WHERE book_id=?", (book_id,)
                )] if "tasks" in source_tables else []
                chapter_ids = [row[0] for row in source.execute(
                    "SELECT id FROM chapters WHERE book_id=?", (book_id,)
                )] if "chapters" in source_tables else []
                has_extraction_data = any(
                    source.execute(f"SELECT 1 FROM {table} WHERE book_id=? LIMIT 1", (book_id,)).fetchone()
                    for table in (
                        "tasks", "extractions", "summaries", "extraction_units",
                        "knowledge_entities", "entity_resolutions",
                    )
                    if table in source_tables
                )
                if "task_logs" in source_tables and task_ids:
                    rows = source.execute(
                        f"SELECT * FROM task_logs WHERE task_id IN ({','.join('?' for _ in task_ids)})",
                        task_ids,
                    ).fetchall()
                    target.executemany(
                        "INSERT OR IGNORE INTO task_logs VALUES(?,?,?,?,?)",
                        [tuple(row) for row in rows],
                    )
                if "chapter_vectors" in source_tables and chapter_ids:
                    rows = source.execute(
                        f"SELECT * FROM chapter_vectors WHERE chapter_id IN ({','.join('?' for _ in chapter_ids)})",
                        chapter_ids,
                    ).fetchall()
                    target.executemany(
                        "INSERT OR IGNORE INTO chapter_vectors VALUES(?,?,?,?)",
                        [tuple(row) for row in rows],
                    )
                for table in (
                    "extraction_units", "task_logs", "extractions", "summaries",
                    "knowledge_entities", "entity_resolutions", "chapter_vectors", "tasks", "chapters",
                ):
                    if table not in source_tables:
                        continue
                    if table == "task_logs":
                        if task_ids:
                            source.execute(
                                f"DELETE FROM task_logs WHERE task_id IN ({','.join('?' for _ in task_ids)})",
                                task_ids,
                            )
                    elif table == "chapter_vectors":
                        if chapter_ids:
                            source.execute(
                                f"DELETE FROM chapter_vectors WHERE chapter_id IN ({','.join('?' for _ in chapter_ids)})",
                                chapter_ids,
                            )
                    elif table == "chapters" and not has_extraction_data:
                        continue
                    else:
                        source.execute(f"DELETE FROM {table} WHERE book_id=?", (book_id,))

    def recover_book_tasks(self):
        for book in self.all("SELECT book_id FROM books"):
            scoped = self.book_database(book["book_id"])
            with scoped.connect() as conn:
                active = conn.execute(
                    "SELECT id FROM tasks WHERE status IN ('pending','running')"
                ).fetchall()
                for task in active:
                    conn.execute(
                        "UPDATE extraction_units SET status='failed',error_message=?,updated_at=? "
                        "WHERE task_id=? AND status='running'",
                        ("服务重启，当前请求已中断", now(), task["id"]),
                    )
                    conn.execute(
                        "UPDATE tasks SET status='failed',error_message=?,current_step=?,updated_at=? WHERE id=?",
                        ("服务重启，任务已中断，请重新执行", "已中断", now(), task["id"]),
                    )
                    self.execute(
                        "UPDATE books SET status='failed',err_message=?,updated_at=? WHERE book_id=?",
                        ("服务重启，任务已中断，请重新执行", now(), book["book_id"]),
                    )

    @staticmethod
    def _widen_message_roles(conn):
        """Allow non-message tree entries on legacy databases.

        Older builds constrained ``messages.role`` to ``user``/``assistant``.
        Compaction, branch-summary, label and session-info entries need wider
        values, so the table is rebuilt once when the old CHECK is detected.
        """

        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='messages'").fetchone()
        definition = (row[0] or "") if row else ""
        if "branchSummary" in definition:
            return
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("ALTER TABLE messages RENAME TO messages_legacy")
        conn.executescript(
            """
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL UNIQUE,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                parent_id TEXT REFERENCES messages(node_id) ON DELETE CASCADE,
                entry_type TEXT NOT NULL DEFAULT 'message',
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'compaction', 'branchSummary', 'label', 'sessionInfo')),
                content TEXT NOT NULL, created_at TEXT NOT NULL,
                summary TEXT, tokens_before INTEGER, kept_from_node_id TEXT, label TEXT, metadata TEXT
            );
            """
        )
        legacy_columns = {info[1] for info in conn.execute("PRAGMA table_info(messages_legacy)").fetchall()}
        columns = [name for name in (
            "id", "node_id", "conversation_id", "parent_id", "entry_type", "role",
            "content", "created_at", "summary", "tokens_before", "kept_from_node_id", "label", "metadata",
        ) if name in legacy_columns]
        if "entry_type" not in columns:
            columns.append("entry_type")
        target = ",".join(columns)
        source = ",".join("'message'" if name == "entry_type" else name for name in columns)
        conn.execute(f"INSERT INTO messages({target}) SELECT {source} FROM messages_legacy")
        conn.execute("DROP TABLE messages_legacy")
        conn.execute("PRAGMA foreign_keys = ON")

    def _routed_database(self, sql, params):
        """Keep direct legacy/test queries useful while production uses book_db explicitly."""

        if hasattr(self, "parent"):
            return self
        lowered = sql.lower()
        if not any(
            f" {table}" in lowered or f" {table}(" in lowered
            for table in BOOK_SCOPED_TABLES
        ):
            return self
        values = list(params or ())
        book_id = next(
            (value for value in values if isinstance(value, str) and value.startswith("book_")),
            None,
        )
        if not book_id:
            # Queries by task/entity/extraction ID are resolved by the
            # cross-book fallback in ``all``/``one`` below.
            book_id = None
        return self.book_database(book_id) if book_id else self

    def _book_databases(self):
        if hasattr(self, "parent"):
            return [self]
        with self.connect() as conn:
            book_ids = [row[0] for row in conn.execute("SELECT book_id FROM books")]
        return [self.book_database(book_id) for book_id in book_ids]

    def all(self, sql, params=()):
        routed = self._routed_database(sql, params)
        if routed is not self:
            return routed.all(sql, params)
        if any(
            f" {table}" in sql.lower() or f" {table}(" in sql.lower()
            for table in BOOK_SCOPED_TABLES
        ) and not hasattr(self, "parent"):
            rows = []
            for database in self._book_databases():
                rows.extend(database.all(sql, params))
            return rows
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def one(self, sql, params=()):
        routed = self._routed_database(sql, params)
        if routed is not self:
            return routed.one(sql, params)
        if any(
            f" {table}" in sql.lower() or f" {table}(" in sql.lower()
            for table in BOOK_SCOPED_TABLES
        ) and not hasattr(self, "parent"):
            for database in self._book_databases():
                row = database.one(sql, params)
                if row:
                    return row
            return None
        with self.connect() as conn:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None

    def execute(self, sql, params=()):
        routed = self._routed_database(sql, params)
        if routed is not self:
            return routed.execute(sql, params)
        with self.connect() as conn:
            return conn.execute(sql, params).rowcount


class BookDatabase(Database):
    def __init__(self, path: Path, parent: Database):
        super().__init__(path)
        self.parent = parent

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, 1}:
                raise RuntimeError(f"Unsupported book database schema version: {version}")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(BOOK_SCHEMA)
            from backend.app.domains.conversation.knowledge_search import initialize_index
            initialize_index(conn)
            character_columns = {row[1] for row in conn.execute("PRAGMA table_info(knowledge_characters)").fetchall()}
            if "frequency" not in character_columns:
                conn.execute(
                    "ALTER TABLE knowledge_characters ADD COLUMN frequency INTEGER NOT NULL DEFAULT 0"
                )
            self._backfill_frequencies(conn)

    def _backfill_frequencies(self, conn):
        """Restore 出现次数 for rows created before ``frequency`` was projected.

        Older builds inserted character rows without a ``frequency`` column, so
        the column migration filled them with ``0``. The projected summaries
        already carry the real count; copy it back once per process.
        """

        key = str(self.path)
        if key in _FREQUENCY_BACKFILLED:
            return
        _FREQUENCY_BACKFILLED.add(key)
        if not conn.execute("SELECT 1 FROM knowledge_characters WHERE frequency=0 LIMIT 1").fetchone():
            return
        row = conn.execute("SELECT content FROM summaries WHERE type='characters'").fetchone()
        if not row or not row[0]:
            return
        try:
            entries = json.loads(row[0])
        except (TypeError, ValueError):
            return
        for entry in entries if isinstance(entries, list) else []:
            name = (entry.get("name") or "").strip()
            frequency = entry.get("frequency") or 0
            if name and frequency > 0:
                conn.execute(
                    "UPDATE knowledge_characters SET frequency=? "
                    "WHERE canonical_name=? AND frequency=0",
                    (frequency, name),
                )
