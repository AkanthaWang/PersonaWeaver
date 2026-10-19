from __future__ import annotations
from backend.app.db.base_repository import SQLiteRepository


class WorkflowRepository(SQLiteRepository):
    def tasks(self, user_id: str, book_id: str | None = None):
        sql = "SELECT t.*,b.title AS book_title FROM tasks t JOIN books b ON t.book_id=b.book_id WHERE b.user_id=?"
        params = [user_id]
        if book_id:
            sql += " AND b.book_id=?"
            params.append(book_id)
        return self.all(sql + " ORDER BY t.created_at DESC LIMIT 200", params)

    def task(self, user_id: str, task_id: str):
        return self.one(
            "SELECT t.* FROM tasks t JOIN books b ON t.book_id=b.book_id WHERE t.id=? AND b.user_id=?",
            (task_id, user_id),
        )

    def logs(self, user_id: str, book_id: str | None = None, limit: int = 50):
        sql = ("SELECT l.* FROM task_logs l JOIN tasks t ON l.task_id=t.id "
               "JOIN books b ON t.book_id=b.book_id WHERE b.user_id=?")
        params = [user_id]
        if book_id:
            sql += " AND b.book_id=?"
            params.append(book_id)
        return self.all(sql + " ORDER BY l.created_at DESC LIMIT ?", (*params, limit))
