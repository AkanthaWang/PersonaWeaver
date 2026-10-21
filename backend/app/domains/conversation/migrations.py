"""Additive conversation schema; never calls providers or rewrites history."""


def initialize_conversations(conn):
    for table in ("model_profiles", "model_settings"):
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if "context_window" not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN context_window INTEGER NOT NULL DEFAULT 32768")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(conversations)")}
    for name, definition in (
        ("book_id", "TEXT REFERENCES books(book_id) ON DELETE SET NULL"),
        ("mode", "TEXT NOT NULL DEFAULT 'assistant'"),
        ("knowledge_enabled", "INTEGER NOT NULL DEFAULT 1"),
        ("memory_enabled", "INTEGER NOT NULL DEFAULT 1"),
    ):
        if name not in columns:
            conn.execute(f"ALTER TABLE conversations ADD COLUMN {name} {definition}")
            if name == "mode":
                conn.execute("UPDATE conversations SET mode='roleplay' WHERE card_id IS NOT NULL")
            if name == "book_id":
                conn.execute("UPDATE conversations SET book_id=(SELECT book_id FROM cards WHERE cards.id=conversations.card_id) "
                             "WHERE card_id IS NOT NULL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversation_mirrors (
            conversation_id TEXT PRIMARY KEY, path TEXT, action TEXT NOT NULL DEFAULT 'sync',
            error TEXT, updated_at TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS conversation_runs (
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            request_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
            status TEXT NOT NULL, parent_id TEXT, message TEXT NOT NULL,
            reply TEXT NOT NULL DEFAULT '', user_node_id TEXT, assistant_node_id TEXT,
            profile_id TEXT, model_snapshot TEXT NOT NULL DEFAULT '{}',
            context_usage TEXT NOT NULL DEFAULT '{}', sources TEXT NOT NULL DEFAULT '[]',
            usage TEXT NOT NULL DEFAULT '{}', error TEXT, result_json TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            PRIMARY KEY(conversation_id,request_id)
        );
        CREATE INDEX IF NOT EXISTS conversation_runs_status ON conversation_runs(status);
    """)
    for operation, source in (("INSERT", "NEW"), ("UPDATE", "NEW"), ("DELETE", "OLD")):
        conn.executescript(f"""
            CREATE TRIGGER IF NOT EXISTS conversation_mirror_message_{operation.lower()}
            AFTER {operation} ON messages BEGIN
                INSERT INTO conversation_mirrors(conversation_id,updated_at)
                VALUES({source}.conversation_id, {source}.created_at)
                ON CONFLICT(conversation_id) DO UPDATE SET action='sync',error=NULL,
                    updated_at=excluded.updated_at;
            END;
        """)
    conn.executescript("""
        CREATE TRIGGER IF NOT EXISTS conversation_mirror_delete
        AFTER DELETE ON conversations BEGIN
            INSERT INTO conversation_mirrors(conversation_id,path,action,updated_at)
            VALUES(OLD.id,OLD.session_file,'delete',OLD.updated_at)
            ON CONFLICT(conversation_id) DO UPDATE SET
                path=OLD.session_file,action='delete',error=NULL;
        END;
    """)
