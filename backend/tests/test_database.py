import sqlite3
from concurrent.futures import ThreadPoolExecutor

from backend.app.db.database import Database


def test_initialize_migrates_legacy_messages_before_creating_entry_index(tmp_path):
    database_path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                card_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            INSERT INTO conversations VALUES ('conversation_1', 'user_1', 'Test', NULL, 'now', 'now');
            INSERT INTO messages(conversation_id, role, content, created_at)
            VALUES ('conversation_1', 'user', 'hello', 'now');
            PRAGMA user_version = 1;
            """
        )

    Database(database_path).initialize()

    with sqlite3.connect(database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(messages)")}
        indexes = {
            row[1]
            for row in connection.execute("PRAGMA index_list(messages)")
        }
        message = connection.execute(
            "SELECT node_id, parent_id, entry_type, role, content FROM messages"
        ).fetchone()

    assert {"node_id", "parent_id", "entry_type"}.issubset(columns)
    assert "messages_by_conversation_entry" in indexes
    assert message == ("message_1", None, "message", "user", "hello")


def test_initialize_adds_chapter_metadata_without_losing_legacy_rows(tmp_path):
    database_path = tmp_path / "legacy_chapters.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE users (
                user_id TEXT PRIMARY KEY, username TEXT, password_hash TEXT, email TEXT,
                avatar TEXT, prompt TEXT, created_at TEXT, updated_at TEXT
            );
            CREATE TABLE books (
                book_id TEXT PRIMARY KEY, user_id TEXT, title TEXT, author TEXT, language TEXT,
                source_type TEXT, file_name TEXT, source_path TEXT, status TEXT, progress INTEGER,
                err_message TEXT, created_at TEXT, updated_at TEXT
            );
            CREATE TABLE chapters (
                id TEXT PRIMARY KEY, book_id TEXT, chapter_no INTEGER, title TEXT,
                content TEXT, word_count INTEGER, UNIQUE(book_id, chapter_no)
            );
            INSERT INTO users VALUES ('user_1','u','hash','','','','now','now');
            INSERT INTO books VALUES ('book_1','user_1','Book','','zh-CN','txt','a.txt','a.txt','ready',0,NULL,'now','now');
            INSERT INTO chapters VALUES ('chapter_1','book_1',1,'第1章','正文',2);
            PRAGMA user_version = 1;
            """
        )

    Database(database_path).initialize()

    with sqlite3.connect(database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(chapters)")}
        chapter = connection.execute(
            "SELECT id,chapter_no,title,content,word_count,source_start,source_end,split_method,confidence,text_path "
            "FROM chapters"
        ).fetchone()

    assert {"source_start", "source_end", "split_method", "confidence"}.issubset(columns)
    assert chapter == ("chapter_1", 1, "第1章", "正文", 2, None, None, "unknown", 0.0, None)
    db = Database(database_path)
    db.initialize()
    assert db.one("SELECT knowledge_revision FROM books WHERE book_id='book_1'")["knowledge_revision"] == 0
    with db.connect() as conn:
        task_columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"cancel_requested", "parent_task_id", "config_fingerprint", "input_fingerprint"} <= task_columns
    assert {"extraction_units", "knowledge_entities", "entity_resolutions"} <= tables


def test_concurrent_book_database_access_initializes_once(tmp_path):
    db = Database(tmp_path / "concurrent.sqlite3")
    db.initialize()

    with ThreadPoolExecutor(max_workers=12) as pool:
        databases = list(pool.map(lambda _: db.book_database("book_concurrent"), range(48)))

    assert all(database is databases[0] for database in databases)
    with databases[0].connect() as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        triggers = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        }
    assert {"chat_index_state", "chat_documents", "chat_fts"} <= tables
    assert "chat_revision_chapters_insert" in triggers


def test_book_database_reads_do_not_require_writer_lock(tmp_path):
    db = Database(tmp_path / "writer.sqlite3")
    db.initialize()
    scoped = db.book_database("book_writer")

    with scoped.connect() as writer:
        writer.execute("BEGIN IMMEDIATE")
        reader = db.book_database("book_writer")
        assert reader.one("SELECT revision FROM chat_index_state WHERE id=1") == {"revision": 0}
