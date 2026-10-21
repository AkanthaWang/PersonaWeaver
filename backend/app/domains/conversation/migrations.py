"""Additive conversation schema; never calls providers or rewrites history."""


def initialize_conversations(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversation_mirrors (
            conversation_id TEXT PRIMARY KEY, path TEXT, action TEXT NOT NULL DEFAULT 'sync',
            error TEXT, updated_at TEXT NOT NULL DEFAULT ''
        );
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
