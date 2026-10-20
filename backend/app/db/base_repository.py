from backend.app.db.database import Database


class SQLiteRepository:
    """Small adapter used by domain repositories without exposing connections."""

    def __init__(self, database: Database):
        self.database = database

    def all(self, sql, params=()):
        return self.database.all(sql, params)

    def one(self, sql, params=()):
        return self.database.one(sql, params)

    def execute(self, sql, params=()):
        return self.database.execute(sql, params)
