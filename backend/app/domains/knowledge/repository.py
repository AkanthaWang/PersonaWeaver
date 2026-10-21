import json

from backend.app.db.database import identifier, now


class KnowledgeRepository:
    def __init__(self, database):
        self.database = database

    def book(self, user_id, book_id):
        return self.database.one("SELECT * FROM books WHERE book_id=? AND user_id=?", (book_id, user_id))

    def db(self, book_id):
        return self.database.book_database(book_id)

    def record_change(self, db, book_id, entity_type, entity_id, operation, before, after, reason, operator_id):
        db.execute(
            "INSERT INTO knowledge_changes"
            "(id,book_id,entity_type,entity_id,operation,before_json,after_json,reason,operator_type,operator_id,batch_id,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (identifier("change"), book_id, entity_type, entity_id, operation,
             json.dumps(before, ensure_ascii=False) if before else None,
             json.dumps(after, ensure_ascii=False) if after else None,
             reason, "user", operator_id, None, now()),
        )

    def valid_evidence(self, db, book_id, payload):
        if payload.chapter_id and not db.one(
            "SELECT id FROM chapters WHERE id=? AND book_id=?", (payload.chapter_id, book_id)
        ):
            return None
        return True
