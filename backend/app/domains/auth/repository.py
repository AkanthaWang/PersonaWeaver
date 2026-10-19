from backend.app.db.base_repository import SQLiteRepository


class AuthRepository(SQLiteRepository):
    def by_username(self, username: str):
        return self.one("SELECT * FROM users WHERE username=?", (username,))

    def by_id(self, user_id: str):
        return self.one("SELECT * FROM users WHERE user_id=?", (user_id,))

    def first_user(self):
        return self.one("SELECT * FROM users ORDER BY created_at, user_id LIMIT 1")

    def create_user(self, user_id: str, username: str, password_hash: str, email: str, stamp: str):
        return self.execute(
            "INSERT INTO users(user_id,username,password_hash,email,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (user_id, username, password_hash, email, stamp, stamp),
        )

    def update_profile(self, user_id: str, username: str, email: str, stamp: str):
        return self.execute(
            "UPDATE users SET username=?,email=?,updated_at=? WHERE user_id=?",
            (username, email, stamp, user_id),
        )

    def update_role(self, user_id: str, prompt: str, avatar, stamp: str):
        return self.execute(
            "UPDATE users SET prompt=?,avatar=?,updated_at=? WHERE user_id=?",
            (prompt, avatar, stamp, user_id),
        )

    def update_avatar(self, user_id: str, avatar: str, stamp: str):
        return self.execute("UPDATE users SET avatar=?,updated_at=? WHERE user_id=?", (avatar, stamp, user_id))

    def update_password(self, user_id: str, password_hash: str, stamp: str):
        with self.database.connect() as conn:
            conn.execute("UPDATE users SET password_hash=?,updated_at=? WHERE user_id=?", (password_hash, stamp, user_id))
            conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))

    def create_session(self, token_hash: str, user_id: str, expires_at: str):
        return self.execute("INSERT INTO sessions VALUES (?, ?, ?)", (token_hash, user_id, expires_at))

    def delete_session(self, token_hash: str):
        return self.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
