from backend.app.db.base_repository import SQLiteRepository


class DocumentRepository(SQLiteRepository):
    def list_for_user(self, user_id: str):
        return self.all("SELECT * FROM books WHERE user_id=? ORDER BY created_at DESC", (user_id,))

    def get_owned(self, user_id: str, book_id: str):
        return self.one("SELECT * FROM books WHERE user_id=? AND book_id=?", (user_id, book_id))

    def chapter_count(self, book_id: str):
        row = self.one("SELECT COUNT(*) AS n FROM chapters WHERE book_id=?", (book_id,))
        return row["n"] if row else 0

    def create_book(self, values):
        return self.execute(
            "INSERT INTO books(book_id,user_id,title,author,language,source_type,file_name,source_path,"
            "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            values,
        )

    def delete_book(self, book_id: str):
        return self.execute("DELETE FROM books WHERE book_id=?", (book_id,))

    def has_active_task(self, book_id: str):
        return bool(self.one(
            "SELECT 1 FROM tasks WHERE book_id=? AND status IN ('pending','running')", (book_id,),
        ))

    def has_extractions(self, book_id: str):
        return bool(self.one("SELECT id FROM extractions WHERE book_id=? LIMIT 1", (book_id,)))

    def chapters(self, book_id: str):
        return self.all(
            "SELECT id,chapter_no,title,word_count,source_start,source_end,split_method,confidence,text_path "
            "FROM chapters WHERE book_id=? ORDER BY chapter_no",
            (book_id,),
        )

    def chapter(self, book_id: str, chapter_id: str):
        return self.one("SELECT * FROM chapters WHERE book_id=? AND id=?", (book_id, chapter_id))

    def extractions(self, book_id: str):
        return self.all(
            "SELECT e.*,c.title FROM extractions e JOIN chapters c ON e.chapter_id=c.id "
            "WHERE e.book_id=? ORDER BY c.chapter_no", (book_id,),
        )

    def summaries(self, book_id: str):
        return self.all("SELECT * FROM summaries WHERE book_id=? ORDER BY type", (book_id,))

    def knowledge_snapshot(self, user_id, book_id):
        with self.database.connect() as conn:
            conn.execute("BEGIN")
            book = conn.execute("SELECT * FROM books WHERE book_id=? AND user_id=?", (book_id, user_id)).fetchone()
            if not book:
                return None
            summaries = [dict(row) for row in conn.execute(
                "SELECT * FROM summaries WHERE book_id=? ORDER BY type", (book_id,),
            )]
            extractions = [dict(row) for row in conn.execute(
                "SELECT e.*,c.title,c.chapter_no FROM extractions e JOIN chapters c ON c.id=e.chapter_id "
                "WHERE e.book_id=? ORDER BY c.chapter_no", (book_id,),
            )]
            pending = [dict(row) for row in conn.execute(
                "SELECT * FROM entity_resolutions WHERE book_id=? AND status='pending' ORDER BY created_at,id",
                (book_id,),
            )]
            return dict(book), summaries, extractions, pending
