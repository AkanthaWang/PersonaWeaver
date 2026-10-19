from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets

from fastapi import HTTPException

from backend.app.db.database import identifier, now


ITERATIONS = 600_000


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest}"


def verify_password(password, encoded):
    if not encoded:
        return False
    _, rounds, salt, expected = encoded.split("$")
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds)).hex()
    return hmac.compare_digest(actual, expected)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def public_user(user):
    return {key: value for key, value in user.items() if key != "password_hash"}


def create_session(db, user_id, days):
    token = secrets.token_urlsafe(48)
    expires = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    db.execute("INSERT INTO sessions VALUES (?, ?, ?)", (token_hash(token), user_id, expires))
    return {"access_token": token, "token_type": "bearer", "expires_in": days * 86400}


def resolve_user(db, authorization):
    if not authorization:
        # Single local workspace: reuse the oldest account so existing books,
        # model settings and avatars remain available after removing login.
        user = db.one("SELECT * FROM users ORDER BY created_at, user_id LIMIT 1")
        if not user:
            stamp = now()
            db.execute(
                "INSERT OR IGNORE INTO users(user_id,username,password_hash,created_at,updated_at) VALUES(?,?,?,?,?)",
                ("local-workspace", "创作者", "", stamp, stamp),
            )
            user = db.one("SELECT * FROM users ORDER BY created_at, user_id LIMIT 1")
        return user
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "请先登录")
    user = db.one(
        "SELECT u.* FROM sessions s JOIN users u ON s.user_id=u.user_id "
        "WHERE s.token_hash=? AND s.expires_at>?",
        (token_hash(token), now()),
    )
    if not user:
        raise HTTPException(401, "登录已过期，请重新登录")
    return user
