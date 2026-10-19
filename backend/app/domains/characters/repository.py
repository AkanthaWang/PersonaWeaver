from __future__ import annotations
from backend.app.db.base_repository import SQLiteRepository


class CharacterRepository(SQLiteRepository):
    def list_for_user(self, user_id: str, book_id: str | None = None):
        sql = "SELECT c.*,b.title AS book_title FROM cards c JOIN books b ON c.book_id=b.book_id WHERE b.user_id=?"
        params = [user_id]
        if book_id:
            sql += " AND b.book_id=?"
            params.append(book_id)
        return self.all(sql + " ORDER BY c.updated_at DESC", params)

    def owned(self, user_id: str, card_id: str):
        return self.one(
            "SELECT c.* FROM cards c JOIN books b ON c.book_id=b.book_id WHERE c.id=? AND b.user_id=?",
            (card_id, user_id),
        )

    def create(self, values):
        return self.execute("INSERT INTO cards VALUES(?,?,?,?,?,?,?)", values)

    def update(self, card_id: str, name: str, intro: str, content: str, stamp: str):
        return self.execute(
            "UPDATE cards SET name=?,intro=?,content=?,updated_at=? WHERE id=?", (name, intro, content, stamp, card_id),
        )

    def delete(self, card_id: str):
        return self.execute("DELETE FROM cards WHERE id=?", (card_id,))

    def summary(self, book_id: str, kind: str):
        return self.one("SELECT content FROM summaries WHERE book_id=? AND type=?", (book_id, kind))
