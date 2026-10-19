from __future__ import annotations
import sqlite3

from fastapi import HTTPException

from backend.app.core.security import create_session, hash_password, public_user, token_hash, verify_password
from backend.app.db.database import identifier, now

from .repository import AuthRepository


class AuthService:
    def __init__(self, db):
        self.db = db
        self.repo = AuthRepository(db)

    def register(self, payload):
        stamp = now()
        try:
            self.repo.create_user(
                identifier("user"), payload.username, hash_password(payload.password), payload.email, stamp,
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "用户名已存在") from exc
        return {"message": "注册成功"}

    def login(self, payload, session_days: int):
        user = self.repo.by_username(payload.username)
        if not user or not verify_password(payload.password, user["password_hash"]):
            raise HTTPException(401, "用户名或密码错误")
        return {**create_session(self.db, user["user_id"], session_days), "user": public_user(user)}

    def logout(self, authorization: str | None):
        token = (authorization or "").partition(" ")[2]
        self.repo.delete_session(token_hash(token))
        return {"ok": True}

    def me(self, user):
        return public_user(user)

    def update_profile(self, user, payload):
        try:
            self.repo.update_profile(user["user_id"], payload.username, payload.email, now())
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "用户名已存在") from exc
        return public_user(self.repo.by_id(user["user_id"]))

    def update_role(self, user, payload):
        if payload.avatar and not payload.avatar.startswith("/api/v1/avatars/"):
            raise HTTPException(422, "仅支持本地上传的头像")
        self.repo.update_role(user["user_id"], payload.prompt, payload.avatar, now())
        return payload.model_dump()

    def change_password(self, user, payload):
        if not verify_password(payload.current_password, user["password_hash"]):
            raise HTTPException(400, "当前密码不正确")
        self.repo.update_password(user["user_id"], hash_password(payload.password), now())
        return {"ok": True, "reauthenticate": True}

    def set_avatar(self, user_id: str, url: str):
        self.repo.update_avatar(user_id, url, now())
